from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunsplit
from urllib.request import Request, urlopen

from .common import (
    USER_AGENT,
    clean_display_text,
    company_cache_key,
    extract_canonical_url,
    extract_job_posting_json_ld,
    extract_open_graph_content,
    log_step,
    normalize_job_id,
    normalize_match_text,
)
from .models import MatchedJob
from .storage import atomic_write, load_jsonl_records
from .workday import RETRIABLE_WORKDAY_ERRORS


def matched_job_key(company_slug: str, greenhouse_job_id: str) -> tuple[str, str]:
    return company_slug, greenhouse_job_id


def save_matched_jobs(matched_jobs_path: Path, jobs: Iterable[MatchedJob]) -> int:
    serialized_lines: list[str] = []
    for job in jobs:
        payload = {
            "company_name": job.company_name,
            "company_slug": job.company_slug,
            "careers_url": job.careers_url,
            "greenhouse_job_id": job.greenhouse_job_id,
            "job_title": job.job_title,
            "job_url": job.job_url,
            "job_location": job.job_location,
            "matched_keywords": job.matched_keywords,
            "matched_role_families": job.matched_role_families,
            "found_date": job.found_date,
            "job_description": job.job_description,
        }
        serialized_lines.append(json.dumps(payload, sort_keys=True))

    text = "\n".join(serialized_lines)
    if text:
        text += "\n"
    atomic_write(matched_jobs_path, text)
    return len(serialized_lines)


def merge_matched_jobs_snapshot(
    existing_jobs: Iterable[MatchedJob],
    refreshed_jobs: Iterable[MatchedJob],
    refreshed_company_keys: set[str],
) -> list[MatchedJob]:
    merged_jobs: list[MatchedJob] = []
    refreshed_jobs_by_key = {
        matched_job_key(job.company_slug, job.greenhouse_job_id): job
        for job in refreshed_jobs
    }

    for job in existing_jobs:
        if company_cache_key(job.company_name) in refreshed_company_keys:
            continue
        merged_jobs.append(job)

    merged_jobs.extend(refreshed_jobs_by_key.values())
    merged_jobs.sort(key=lambda job: (job.company_name.casefold(), job.job_title.casefold(), job.greenhouse_job_id))
    return merged_jobs


def load_matched_jobs_snapshot(matched_jobs_path: Path) -> list[MatchedJob]:
    jobs: list[MatchedJob] = []
    for record in load_jsonl_records(matched_jobs_path):
        company_slug = clean_display_text(str(record.get("company_slug") or ""))
        job_id = normalize_job_id(record.get("greenhouse_job_id"))
        if not company_slug or not job_id:
            continue
        jobs.append(
            MatchedJob(
                company_name=clean_display_text(str(record.get("company_name") or "")),
                company_slug=company_slug,
                careers_url=clean_display_text(str(record.get("careers_url") or "")),
                greenhouse_job_id=job_id,
                job_title=clean_display_text(str(record.get("job_title") or "")),
                job_url=clean_display_text(str(record.get("job_url") or "")),
                job_location=clean_display_text(str(record.get("job_location") or "")),
                matched_keywords=list(record.get("matched_keywords") or []),
                matched_role_families=list(record.get("matched_role_families") or []),
                found_date=clean_display_text(str(record.get("found_date") or "")),
                job_description=str(record.get("job_description") or ""),
            )
        )
    return jobs


def is_workday_job_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host.endswith("myworkdayjobs.com") or host.endswith("workdayjobs.com")


def normalize_workday_job_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return clean_display_text(url).rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", ""))


def fetch_workday_detail_html(url: str, *, timeout_seconds: int) -> tuple[str, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    for attempt in range(2):
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                final_url = response.geturl()
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace"), final_url
        except RETRIABLE_WORKDAY_ERRORS + (URLError,):
            if attempt == 1:
                raise
    raise RuntimeError("Workday detail fetch exhausted retries without returning a response")


def normalize_workday_locality_name(locality: str) -> str:
    cleaned = clean_display_text(locality)
    if not cleaned:
        return ""
    cleaned = re.sub(r"\s*-\s*[A-Z0-9]+$", "", cleaned)
    state_city_match = re.match(r"^(?P<state>[A-Z]{2})\s+(?P<city>.+)$", cleaned)
    if state_city_match is not None:
        return f"{state_city_match.group('city')}, {state_city_match.group('state')}"
    return cleaned


def normalize_workday_snapshot_location(job: MatchedJob, job_posting: dict) -> str:
    normalized_title = normalize_match_text(job.job_title)
    normalized_existing_location = normalize_match_text(job.job_location)

    applicant_location = job_posting.get("applicantLocationRequirements") or {}
    applicant_country = clean_display_text(str(applicant_location.get("name") or ""))
    job_location = job_posting.get("jobLocation") or {}
    address = job_location.get("address") or {}
    locality = normalize_workday_locality_name(str(address.get("addressLocality") or ""))
    country = clean_display_text(str(address.get("addressCountry") or ""))
    job_location_type = normalize_match_text(str(job_posting.get("jobLocationType") or ""))

    is_us_telecommute = job_location_type == "telecommute" and "united states" in normalize_match_text(applicant_country or country)
    is_hybrid = "hybrid" in normalized_title or "hybrid" in normalized_existing_location

    if is_hybrid:
        if locality:
            return f"Hybrid - {locality}"
        if applicant_country:
            return f"Hybrid - {applicant_country}"
        if country:
            return f"Hybrid - {country}"
        return "Hybrid"

    if is_us_telecommute and not is_hybrid:
        return "Remote - United States"

    if locality:
        return locality
    if country:
        return country
    if is_us_telecommute:
        return "Remote - United States"
    return job.job_location


def refresh_workday_snapshot_job(job: MatchedJob, *, timeout_seconds: int) -> MatchedJob:
    detail_html, final_url = fetch_workday_detail_html(job.job_url, timeout_seconds=timeout_seconds)
    job_posting = extract_job_posting_json_ld(detail_html)
    canonical_url = extract_canonical_url(detail_html) or normalize_workday_job_url(final_url)
    description = clean_display_text(str(job_posting.get("description") or "")) or extract_open_graph_content(detail_html, "og:description")
    title = clean_display_text(str(job_posting.get("title") or "")) or job.job_title
    location = normalize_workday_snapshot_location(job, job_posting)

    return MatchedJob(
        company_name=job.company_name,
        company_slug=job.company_slug,
        careers_url=job.careers_url,
        greenhouse_job_id=job.greenhouse_job_id,
        job_title=title,
        job_url=canonical_url,
        job_location=location,
        matched_keywords=job.matched_keywords,
        matched_role_families=job.matched_role_families,
        found_date=job.found_date,
        job_description=description or job.job_description,
    )


def backfill_workday_snapshot_details(
    *,
    company_names: list[str],
    timeout_seconds: int,
    matched_jobs_path: Path,
) -> int:
    selected_company_keys = {company_cache_key(name) for name in company_names if clean_display_text(name)}
    matched_jobs = load_matched_jobs_snapshot(matched_jobs_path)
    refreshed_jobs: list[MatchedJob] = []
    updated = 0

    for job in matched_jobs:
        if not is_workday_job_url(job.job_url):
            refreshed_jobs.append(job)
            continue
        if selected_company_keys and company_cache_key(job.company_name) not in selected_company_keys:
            refreshed_jobs.append(job)
            continue

        try:
            refreshed = refresh_workday_snapshot_job(job, timeout_seconds=timeout_seconds)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            log_step(f"{job.company_name}: failed to backfill Workday snapshot detail for {job.greenhouse_job_id}: {exc}")
            refreshed_jobs.append(job)
            continue

        if (
            refreshed.job_url != job.job_url
            or refreshed.job_description != job.job_description
            or refreshed.job_title != job.job_title
            or refreshed.job_location != job.job_location
        ):
            updated += 1
        refreshed_jobs.append(refreshed)

    if updated:
        save_matched_jobs(matched_jobs_path, refreshed_jobs)
    return updated