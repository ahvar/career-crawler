#!/usr/bin/env python3
"""
ATS-aware job crawler for a fixed list of target companies.

The crawler intentionally skips Gregslist and company-homepage discovery. It:
- generates likely Greenhouse board slugs for each target company
- probes the Greenhouse public jobs API until it finds a live board
- falls back to configured Workday boards when appropriate
- fetches job detail payloads for matched roles
- filters jobs by target title families
- writes a refreshed matched-jobs snapshot to crawler_cache/matched_jobs.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError

from ats.config import (
    WORKDAY_BOARD_HINTS_PATH,
    load_greenhouse_slug_hints,
    load_phenom_search_hints,
    load_workday_board_hints,
)
from ats.common import clean_display_text, company_cache_key, dedupe_preserve_order, log_step, normalize_job_id, normalize_match_text
from ats.greenhouse import GreenhouseCrawler
from ats.models import CompanyAssessment, CrawlRun, JobMatchResult, MatchedJob, TargetCompany
from ats.reporting import (
    format_company_ats_report as render_company_ats_report,
    format_intake_workday_report as render_intake_workday_report,
    format_matched_job_urls,
    format_matched_jobs,
    format_results,
    format_workday_discovery_report,
)
from ats.registry import (
    build_company_registry_records as build_company_registry_records_from_sources,
    categorize_company_registry_records,
    finalize_company_registry_record,
    get_workday_check_candidates,
    load_company_names_from_text_file as load_company_names_from_text_path,
    make_default_company_registry_record,
    normalize_company_registry_record,
)
from ats.storage import (
    atomic_write,
    count_jsonl_rows,
    count_text_rows,
    load_company_registry_records as load_company_registry_records_from_path,
    load_company_revisit_records as load_company_revisit_records_from_path,
    load_company_search_cache as load_company_search_cache_from_path,
    load_job_tracking_records as load_job_tracking_records_from_path,
    load_jsonl_records,
    load_non_greenhouse_companies as load_non_greenhouse_companies_from_path,
    save_company_registry_records as save_company_registry_records_to_path,
    save_company_revisit_records as save_company_revisit_records_to_path,
    save_company_search_cache as save_company_search_cache_to_path,
    save_job_tracking_records as save_job_tracking_records_to_path,
    save_non_greenhouse_companies as save_non_greenhouse_companies_to_path,
)
from ats.tracking import format_tracking_report as render_tracking_report
from ats.phenompeople import PhenomPeopleCrawler, has_phenom_search_hint
from ats.workday_discovery import WorkdayBoardDiscoverer
from ats.workday import WorkdayCrawler, has_workday_board_hint


DEFAULT_DELAY_SECONDS = 0.4
DEFAULT_CONCURRENCY = 4
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_NON_GREENHOUSE_REVISIT_DAYS = 30
DEFAULT_WORKDAY_DISCOVERY_LIMIT = 10
VALID_JOB_TRACKING_STATUSES = ("pending_review", "applied", "revisit_later", "not_a_fit", "archived")

CACHE_DIR = Path("crawler_cache")
MATCHED_JOBS_PATH = CACHE_DIR / "matched_jobs.jsonl"
SEARCHED_COMPANIES_PATH = CACHE_DIR / "careers_scraped.jsonl"
NON_GREENHOUSE_COMPANIES_PATH = CACHE_DIR / "non_greenhouse_companies.txt"
JOB_TRACKING_PATH = CACHE_DIR / "job_tracking.jsonl"
COMPANY_REVISIT_PATH = CACHE_DIR / "company_revisit.jsonl"
COMPANY_REGISTRY_PATH = CACHE_DIR / "company_registry.jsonl"
ARCHIVE_DIR = CACHE_DIR / "archive"
NEW_COMPANIES_PATH = Path("new_companies.txt")

DEFAULT_TARGET_COMPANIES = (
    "Affirm",
    "Striveworks",
    "Instacart",
    "Elastic",
    "Doximity",
    "Reddit",
    "Upside",
    "Expedia Group",
    "LogicMonitor",
    "PwC",
    "Vercel",
    "AlertMedia",
    "SciPlay",
    "Wise",
    "inKind",
    "Rubrik",
    "GroceryTV",
    "Rapid7",
    "Lansweeper",
    "CDW",
    "Optimal",
    "ARM",
    "Sysco LABS",
    "8am",
    "CrowdStrike",
    "ReUp Education",
    "Udemy",
    "ServiceNow",
    "CiscoThousandEyes",
    "Dealerware",
    "Imprivata",
    "Navan",
    "Apex Fintech Solutions",
    "BigCommerce",
    "Snap Inc.",
    "BAE Systems, Inc.",
    "Motive",
    "Riot Platforms, Inc.",
    "Closinglock",
    "CDW",
    "Imprivata",
    "Ericsson",
    "Atlassian",
    "UL Solutions",
    "Zello",
    "SEON",
    "VISA",
    "Spectrum",
    "2K",
    "MongoDB",
    "Upstart",
    "Dscout",
    "Invoice Home",
    "Snap! Mobile",
    "Aceable",
    "Metropolis Technologies",
    "CAIS",
    "Flatfile",
    "Dropbox",
    "Agora RE",
    "Huntress",
    "M-Files",
    "Moov",
    "Hudson River Trading",
    "Babylist",
    "Unchained",
    "Rev",
    "The Knot Worldwide",
    "Citylitics",
    "Airtable",
    "ConverseNow",
    "Sprinklr",
    "Origis Energy",
    "Arganteal Corporation",
    "All Options",
    "Orchard",
    "Pensa Systems",
    "Darktrace",
    "ActiveProspect",
    "Pattern Bioscience",
    "CoStar Group",
    "DevDocs",
    "GSD&M",
    "Peddle",
    "Avathon",
    "Gamurs Group",
    "Conduent",
    "SmartBiz Loans",
)

GREENHOUSE_SLUG_HINTS = load_greenhouse_slug_hints(normalize_text=clean_display_text)
WORKDAY_BOARD_HINTS = load_workday_board_hints(
    normalize_company_key=company_cache_key,
    normalize_text=clean_display_text,
)
PHENOM_SEARCH_HINTS = load_phenom_search_hints(
    normalize_company_key=company_cache_key,
    normalize_text=clean_display_text,
)

class CrawlError(RuntimeError):
    """Raised when crawling cannot proceed safely."""


def ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)


def ensure_tracking_files() -> None:
    ensure_cache_dir()
    for path in (JOB_TRACKING_PATH, COMPANY_REVISIT_PATH, COMPANY_REGISTRY_PATH):
        if not path.exists():
            path.write_text("", encoding="utf-8")


def save_matched_jobs(jobs: Iterable[MatchedJob]) -> int:
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
    atomic_write(MATCHED_JOBS_PATH, text)
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


def summarize_output_stats() -> str:
    ensure_cache_dir()
    ensure_tracking_files()
    archived_match_files = sorted(ARCHIVE_DIR.glob("matched_jobs*.jsonl"))
    lines = [
        f"Output file: {MATCHED_JOBS_PATH}",
        f"Current matched jobs: {count_jsonl_rows(MATCHED_JOBS_PATH)}",
        f"Searched companies cache: {len(load_company_search_cache())}",
        f"Known non-Greenhouse companies: {count_text_rows(NON_GREENHOUSE_COMPANIES_PATH)}",
        f"Company ATS registry records: {count_jsonl_rows(COMPANY_REGISTRY_PATH)}",
        f"Tracked jobs: {count_jsonl_rows(JOB_TRACKING_PATH)}",
        f"Tracked company revisits: {count_jsonl_rows(COMPANY_REVISIT_PATH)}",
        f"Archived matched-job files: {len(archived_match_files)}",
    ]
    return "\n".join(lines)


def build_slug_candidates(company_name: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", company_name.lower())
    if not tokens:
        return []

    hinted = list(GREENHOUSE_SLUG_HINTS.get(company_name, ()))
    generated = [
        "".join(tokens),
        "-".join(tokens),
        "_".join(tokens),
    ]
    if len(tokens) > 1:
        generated.extend(
            [
                tokens[0],
                tokens[-1],
                f"{tokens[0]}{tokens[-1]}",
                f"{tokens[0]}-{tokens[-1]}",
            ]
        )

    cleaned_candidates: list[str] = []
    for candidate in hinted + generated:
        cleaned = candidate.strip("-_")
        if cleaned:
            cleaned_candidates.append(cleaned)
    return dedupe_preserve_order(cleaned_candidates)


def build_target_companies(company_names: Iterable[str]) -> list[TargetCompany]:
    targets: list[TargetCompany] = []
    seen_company_keys: set[str] = set()
    for company_name in company_names:
        company_name = clean_display_text(company_name)
        if not company_name:
            continue
        company_key = company_cache_key(company_name)
        if company_key in seen_company_keys:
            continue
        seen_company_keys.add(company_key)
        targets.append(
            TargetCompany(
                name=company_name,
                slug_candidates=tuple(build_slug_candidates(company_name)),
            )
        )
    return targets


def matched_job_key(company_slug: str, greenhouse_job_id: str) -> tuple[str, str]:
    return company_slug, greenhouse_job_id


def load_matched_jobs_snapshot() -> list[MatchedJob]:
    jobs: list[MatchedJob] = []
    for record in load_jsonl_records(MATCHED_JOBS_PATH):
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


def load_job_tracking_records() -> dict[tuple[str, str], dict]:
    ensure_tracking_files()
    return load_job_tracking_records_from_path(JOB_TRACKING_PATH)


def save_job_tracking_records(records: dict[tuple[str, str], dict]) -> int:
    return save_job_tracking_records_to_path(JOB_TRACKING_PATH, records)


def load_company_revisit_records() -> dict[str, dict]:
    ensure_tracking_files()
    return load_company_revisit_records_from_path(COMPANY_REVISIT_PATH)


def save_company_revisit_records(records: dict[str, dict]) -> int:
    return save_company_revisit_records_to_path(COMPANY_REVISIT_PATH, records)


def load_company_registry_records() -> dict[str, dict]:
    ensure_tracking_files()
    return load_company_registry_records_from_path(COMPANY_REGISTRY_PATH)


def save_company_registry_records(records: dict[str, dict]) -> int:
    return save_company_registry_records_to_path(COMPANY_REGISTRY_PATH, records)


def build_current_company_registry_records(
    *,
    search_cache: dict[str, dict] | None = None,
    non_greenhouse_cache: dict[str, str] | None = None,
    company_revisits: dict[str, dict] | None = None,
    existing_records: dict[str, dict] | None = None,
    greenhouse_assessments: Iterable[CompanyAssessment] = (),
    workday_assessments: Iterable[CompanyAssessment] = (),
    other_ats_assessments: Iterable[CompanyAssessment] = (),
) -> dict[str, dict]:
    return build_company_registry_records_from_sources(
        search_records=search_cache if search_cache is not None else load_company_search_cache(),
        non_greenhouse_records=non_greenhouse_cache if non_greenhouse_cache is not None else load_non_greenhouse_companies(),
        revisit_records=company_revisits if company_revisits is not None else load_company_revisit_records(),
        registry_records=existing_records if existing_records is not None else load_company_registry_records(),
        default_company_names=DEFAULT_TARGET_COMPANIES,
        workday_board_hints=WORKDAY_BOARD_HINTS,
        greenhouse_assessments=greenhouse_assessments,
        workday_assessments=workday_assessments,
        other_ats_assessments=other_ats_assessments,
    )


def sync_company_registry(
    *,
    search_cache: dict[str, dict] | None = None,
    non_greenhouse_cache: dict[str, str] | None = None,
    company_revisits: dict[str, dict] | None = None,
    greenhouse_assessments: Iterable[CompanyAssessment] = (),
    workday_assessments: Iterable[CompanyAssessment] = (),
    other_ats_assessments: Iterable[CompanyAssessment] = (),
) -> int:
    records = build_current_company_registry_records(
        search_cache=search_cache,
        non_greenhouse_cache=non_greenhouse_cache,
        company_revisits=company_revisits,
        greenhouse_assessments=greenhouse_assessments,
        workday_assessments=workday_assessments,
        other_ats_assessments=other_ats_assessments,
    )
    return save_company_registry_records(records)


def format_company_ats_report() -> str:
    records = build_current_company_registry_records()
    categories = categorize_company_registry_records(records)
    return render_company_ats_report(records, categories)


def load_company_names_from_text_file(path: Path) -> list[str]:
    return load_company_names_from_text_path(path)


def format_intake_workday_report(path: Path = NEW_COMPANIES_PATH) -> str:
    records = build_current_company_registry_records()
    company_names = load_company_names_from_text_file(path)
    return render_intake_workday_report(records, company_names, path)


def record_missing_workday_board(company_name: str, detail: str) -> dict:
    normalized_company_name = clean_display_text(company_name)
    company_slug = company_cache_key(normalized_company_name)
    today = date.today()
    today_iso = today.isoformat()

    revisit_records = load_company_revisit_records()
    revisit_record = revisit_records.get(company_slug) or build_non_greenhouse_revisit_record(
        company_name=normalized_company_name,
        last_checked=today_iso,
        next_revisit=(today + timedelta(days=DEFAULT_NON_GREENHOUSE_REVISIT_DAYS)).isoformat(),
    )
    revisit_record = {
        **revisit_record,
        "company_name": normalized_company_name,
        "board_type": "ats_research",
        "last_checked": today_iso,
        "next_revisit": (today + timedelta(days=DEFAULT_NON_GREENHOUSE_REVISIT_DAYS)).isoformat(),
        "reason": "Greenhouse board not found; Workday board not found; investigate alternate ATS/job board.",
        "notes": detail,
    }
    revisit_records[company_slug] = revisit_record
    save_company_revisit_records(revisit_records)

    existing_records = load_company_registry_records()
    record = existing_records.get(company_slug) or make_default_company_registry_record(
        company_slug,
        normalized_company_name,
        WORKDAY_BOARD_HINTS,
    )
    record.update(
        {
            "company_name": normalized_company_name,
            "workday_status": "not_found",
            "workday_status_detail": detail,
            "workday_last_checked": today_iso,
            "last_overall_check": today_iso,
        }
    )
    existing_records[company_slug] = finalize_company_registry_record(record, revisit_record)
    save_company_registry_records(existing_records)
    return existing_records[company_slug]


async def discover_workday_boards(
    *,
    company_names: list[str],
    limit: int,
    delay: float,
    concurrency: int,
    timeout: int,
    apply_confirmed_results: bool,
    apply_not_found_results: bool,
) -> list[dict]:
    records = build_current_company_registry_records()
    if company_names:
        record_names_by_key = {
            company_cache_key(record["company_name"]): record["company_name"]
            for record in records.values()
        }
        candidate_names = dedupe_preserve_order(
            record_names_by_key.get(company_cache_key(company_name), clean_display_text(company_name))
            for company_name in company_names
        )
    else:
        candidates = get_workday_check_candidates(records)
        candidate_names = [record["company_name"] for record in candidates]
    candidate_names = candidate_names[:limit]

    discoverer = WorkdayBoardDiscoverer(
        delay_seconds=delay,
        concurrency=concurrency,
        timeout_seconds=timeout,
    )
    results = await discoverer.discover_companies(candidate_names)

    if apply_confirmed_results or apply_not_found_results:
        for result in results:
            if apply_confirmed_results and result["status"] == "confirmed":
                promote_company_to_workday(
                    company_name=result["company_name"],
                    tenant=result["tenant"],
                    site_id=result["site_id"],
                    board_url=result["board_url"],
                )
            elif apply_not_found_results and result["status"] == "not_found":
                record_missing_workday_board(result["company_name"], result["detail"])

    return results


def load_workday_hint_payload() -> dict[str, dict[str, str]]:
    if not WORKDAY_BOARD_HINTS_PATH.exists():
        return {}
    try:
        payload = json.loads(WORKDAY_BOARD_HINTS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_workday_hint_payload(payload: dict[str, dict[str, str]]) -> None:
    atomic_write(WORKDAY_BOARD_HINTS_PATH, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def promote_company_to_workday(
    *,
    company_name: str,
    tenant: str,
    site_id: str,
    board_url: str,
) -> dict:
    normalized_company_name = clean_display_text(company_name)
    if not normalized_company_name:
        raise CrawlError("Company name is required for Workday promotion.")

    normalized_tenant = clean_display_text(tenant)
    normalized_site_id = clean_display_text(site_id)
    normalized_board_url = clean_display_text(board_url)
    if not normalized_tenant or not normalized_site_id or not normalized_board_url:
        raise CrawlError("Workday promotion requires tenant, site id, and board URL.")

    payload = load_workday_hint_payload()
    payload[normalized_company_name] = {
        "tenant": normalized_tenant,
        "site_id": normalized_site_id,
        "board_url": normalized_board_url,
    }
    save_workday_hint_payload(payload)

    company_slug = company_cache_key(normalized_company_name)
    WORKDAY_BOARD_HINTS[company_slug] = {
        "tenant": normalized_tenant,
        "site_id": normalized_site_id,
        "board_url": normalized_board_url,
    }

    revisit_records = load_company_revisit_records()
    today = date.today()
    today_iso = today.isoformat()
    revisit_record = revisit_records.get(company_slug)
    if revisit_record is None:
        revisit_record = {
            "company_slug": company_slug,
            "company_name": normalized_company_name,
            "board_type": "workday",
            "last_checked": today_iso,
            "next_revisit": (today + timedelta(days=DEFAULT_NON_GREENHOUSE_REVISIT_DAYS)).isoformat(),
            "reason": "Confirmed Workday board; refresh crawler for Austin/US-remote roles.",
            "notes": "Validated Workday board configuration.",
        }
    else:
        revisit_record = {
            **revisit_record,
            "company_name": normalized_company_name,
            "board_type": "workday",
            "last_checked": today_iso,
            "reason": "Confirmed Workday board; refresh crawler for Austin/US-remote roles.",
            "notes": clean_display_text(str(revisit_record.get("notes") or "")) or "Validated Workday board configuration.",
        }
    revisit_records[company_slug] = revisit_record
    save_company_revisit_records(revisit_records)

    existing_records = load_company_registry_records()
    record = existing_records.get(company_slug) or make_default_company_registry_record(
        company_slug,
        normalized_company_name,
        WORKDAY_BOARD_HINTS,
    )
    record.update(
        {
            "company_name": normalized_company_name,
            "workday_status": "confirmed",
            "workday_board_url": normalized_board_url,
            "workday_tenant": normalized_tenant,
            "workday_site_id": normalized_site_id,
            "workday_last_checked": today_iso,
            "workday_status_detail": "Confirmed Workday board from manual validation.",
            "last_overall_check": today_iso,
        }
    )
    existing_records[company_slug] = finalize_company_registry_record(record, revisit_record)
    save_company_registry_records(existing_records)
    return existing_records[company_slug]


def parse_iso_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def build_non_greenhouse_revisit_record(company_name: str, last_checked: str, next_revisit: str) -> dict:
    return {
        "company_slug": company_cache_key(company_name),
        "company_name": company_name,
        "board_type": "ats_research",
        "last_checked": last_checked,
        "next_revisit": next_revisit,
        "reason": "Greenhouse board not found; investigate alternate ATS/job board.",
        "notes": "Check likely systems such as Workday, Lever, Ashby, SmartRecruiters, and direct company-hosted boards.",
    }


def sync_non_greenhouse_company_revisits(
    *,
    search_cache: dict[str, dict] | None = None,
    non_greenhouse_cache: dict[str, str] | None = None,
    today_iso: str | None = None,
) -> int:
    records = load_company_revisit_records()
    search_records = search_cache if search_cache is not None else load_company_search_cache()
    non_greenhouse_companies = (
        non_greenhouse_cache if non_greenhouse_cache is not None else load_non_greenhouse_companies()
    )
    fallback_date = today_iso or date.today().isoformat()
    created = 0

    for company_key, company_name in non_greenhouse_companies.items():
        existing = records.get(company_key)
        if existing is not None:
            continue

        search_record = search_records.get(company_key, {})
        last_checked = clean_display_text(str(search_record.get("last_scraped") or "")) or fallback_date
        parsed_last_checked = parse_iso_date(last_checked) or parse_iso_date(fallback_date) or date.today()
        next_revisit = (parsed_last_checked + timedelta(days=DEFAULT_NON_GREENHOUSE_REVISIT_DAYS)).isoformat()
        records[company_key] = build_non_greenhouse_revisit_record(
            company_name=company_name,
            last_checked=last_checked,
            next_revisit=next_revisit,
        )
        created += 1

    if created:
        save_company_revisit_records(records)
    return created


def get_matched_job_snapshot_record(company_slug: str, greenhouse_job_id: str) -> MatchedJob | None:
    for job in load_matched_jobs_snapshot():
        if matched_job_key(job.company_slug, job.greenhouse_job_id) == (company_slug, greenhouse_job_id):
            return job
    return None


def upsert_job_tracking_record(
    *,
    company_slug: str,
    greenhouse_job_id: str,
    status: str,
    review_date: str | None,
    application_date: str | None,
    next_action_date: str | None,
    notes: str | None,
    match_rationale: str | None,
) -> dict:
    if status not in VALID_JOB_TRACKING_STATUSES:
        raise CrawlError(f"Unsupported job status: {status}")

    records = load_job_tracking_records()
    key = matched_job_key(company_slug, normalize_job_id(greenhouse_job_id))
    existing = records.get(key)
    snapshot_job = get_matched_job_snapshot_record(company_slug, greenhouse_job_id)
    if existing is None and snapshot_job is None:
        raise CrawlError(
            f"Job {greenhouse_job_id} for company slug '{company_slug}' was not found in the current snapshot or tracking overlay."
        )

    today_iso = date.today().isoformat()
    base_record = existing or {
        "company_slug": company_slug,
        "greenhouse_job_id": normalize_job_id(greenhouse_job_id),
        "job_url": snapshot_job.job_url if snapshot_job is not None else "",
        "status": "pending_review",
        "review_date": "",
        "application_date": "",
        "next_action_date": "",
        "notes": "",
        "match_rationale": "",
    }

    updated = {
        **base_record,
        "status": status,
        "job_url": base_record.get("job_url") or (snapshot_job.job_url if snapshot_job is not None else ""),
        "review_date": review_date if review_date is not None else (base_record.get("review_date") or today_iso),
        "application_date": application_date if application_date is not None else base_record.get("application_date", ""),
        "next_action_date": next_action_date if next_action_date is not None else base_record.get("next_action_date", ""),
        "notes": notes if notes is not None else base_record.get("notes", ""),
        "match_rationale": match_rationale if match_rationale is not None else base_record.get("match_rationale", ""),
    }

    if status == "applied" and not updated["application_date"]:
        updated["application_date"] = today_iso
    if status != "applied" and application_date == "":
        updated["application_date"] = ""

    records[key] = updated
    save_job_tracking_records(records)
    return updated


def backfill_pending_review_records(*, review_date: str | None, notes: str | None, match_rationale: str | None) -> int:
    tracked_records = load_job_tracking_records()
    matched_jobs = load_matched_jobs_snapshot()
    today_iso = date.today().isoformat()
    created = 0

    for job in matched_jobs:
        key = matched_job_key(job.company_slug, job.greenhouse_job_id)
        if key in tracked_records:
            continue
        tracked_records[key] = {
            "company_slug": job.company_slug,
            "greenhouse_job_id": job.greenhouse_job_id,
            "job_url": job.job_url,
            "status": "pending_review",
            "review_date": review_date if review_date is not None else today_iso,
            "application_date": "",
            "next_action_date": "",
            "notes": notes if notes is not None else "Backfilled from matched_jobs.jsonl snapshot.",
            "match_rationale": match_rationale if match_rationale is not None else "Auto-backfilled pending-review record for an existing matched job.",
        }
        created += 1

    if created:
        save_job_tracking_records(tracked_records)
    return created


def format_tracking_report() -> str:
    ensure_tracking_files()
    return render_tracking_report(
        today=date.today(),
        matched_jobs=load_matched_jobs_snapshot(),
        tracked_jobs=load_job_tracking_records(),
        company_revisits=load_company_revisit_records(),
    )


def load_company_search_cache() -> dict[str, dict]:
    return load_company_search_cache_from_path(SEARCHED_COMPANIES_PATH)


def save_company_search_cache(records_by_company: dict[str, dict]) -> int:
    return save_company_search_cache_to_path(SEARCHED_COMPANIES_PATH, records_by_company)


def load_non_greenhouse_companies() -> dict[str, str]:
    return load_non_greenhouse_companies_from_path(NON_GREENHOUSE_COMPANIES_PATH)


def save_non_greenhouse_companies(companies_by_key: dict[str, str]) -> int:
    return save_non_greenhouse_companies_to_path(NON_GREENHOUSE_COMPANIES_PATH, companies_by_key)


def build_cached_assessment(company_name: str, record: dict, status: str) -> CompanyAssessment:
    resolved_slug = clean_display_text(str(record.get("resolved_slug") or ""))
    board_url = clean_display_text(str(record.get("board_url") or ""))
    source = clean_display_text(str(record.get("source") or "greenhouse")) or "greenhouse"
    jobs_seen = record.get("jobs_seen")
    matched_job_count = record.get("matched_job_count")
    matched_jobs = [None] * matched_job_count if isinstance(matched_job_count, int) and matched_job_count > 0 else []
    return CompanyAssessment(
        name=company_name,
        attempted_slugs=[],
        resolved_slug=resolved_slug or None,
        board_url=board_url or None,
        status=status,
        source=source,
        jobs_seen=jobs_seen if isinstance(jobs_seen, int) else 0,
        matched_jobs=matched_jobs,
    )


def build_search_record(assessment: CompanyAssessment, today_iso: str) -> dict:
    return {
        "company_name": assessment.name,
        "last_scraped": today_iso,
        "board_url": assessment.board_url,
        "resolved_slug": assessment.resolved_slug,
        "jobs_seen": assessment.jobs_seen,
        "matched_job_count": len(assessment.matched_jobs),
        "status": assessment.status,
        "source": assessment.source,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ATS-aware job crawler for target companies.")
    parser.add_argument(
        "--company",
        action="append",
        default=[],
        help="Limit the run to one or more company names. Repeat the flag to provide multiple names.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=len(DEFAULT_TARGET_COMPANIES),
        help=f"Maximum number of companies to process. Default: {len(DEFAULT_TARGET_COMPANIES)}.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
        help=f"Minimum delay in seconds between API requests. Default: {DEFAULT_DELAY_SECONDS}.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Maximum in-flight API requests. Default: {DEFAULT_CONCURRENCY}.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-request timeout in seconds. Default: {DEFAULT_TIMEOUT_SECONDS}.",
    )
    parser.add_argument(
        "--show-cache-stats",
        action="store_true",
        help="Print matched-job output and archive counts, then exit.",
    )
    parser.add_argument(
        "--show-company-list",
        action="store_true",
        help="Print the default target company list and exit.",
    )
    parser.add_argument(
        "--show-tracking-report",
        action="store_true",
        help="Print a report that joins matched jobs with job/company tracking overlays, then exit.",
    )
    parser.add_argument(
        "--show-company-ats-report",
        action="store_true",
        help="Print a report summarizing which companies are confirmed Greenhouse, confirmed Workday, or queued for Workday research.",
    )
    parser.add_argument(
        "--show-intake-workday-report",
        action="store_true",
        help="Print a focused ATS report for companies listed in new_companies.txt.",
    )
    parser.add_argument(
        "--set-company-workday-board",
        action="store_true",
        help="Record a validated Workday board in workday_board_hints.json and the company ATS registry.",
    )
    parser.add_argument(
        "--discover-workday-boards",
        action="store_true",
        help="Probe the current Workday discovery queue for valid Workday board patterns.",
    )
    parser.add_argument(
        "--apply-discovered-workday-boards",
        action="store_true",
        help="Persist confirmed Workday discovery results instead of running in dry-run mode.",
    )
    parser.add_argument(
        "--apply-workday-not-found-results",
        action="store_true",
        help="Persist clean Workday not_found discovery results so Greenhouse-not-found companies advance into check_other_ats.",
    )
    parser.add_argument(
        "--workday-discovery-limit",
        type=int,
        default=DEFAULT_WORKDAY_DISCOVERY_LIMIT,
        help=f"Maximum number of queued companies to probe for Workday boards. Default: {DEFAULT_WORKDAY_DISCOVERY_LIMIT}.",
    )
    parser.add_argument(
        "--company-name",
        help="Canonical company name used with --set-company-workday-board.",
    )
    parser.add_argument(
        "--workday-tenant",
        help="Workday tenant used with --set-company-workday-board.",
    )
    parser.add_argument(
        "--workday-site-id",
        help="Workday site id used with --set-company-workday-board.",
    )
    parser.add_argument(
        "--workday-board-url",
        help="Workday board URL used with --set-company-workday-board.",
    )
    parser.add_argument(
        "--sync-non-greenhouse-revisits",
        action="store_true",
        help="Backfill non-Greenhouse companies into crawler_cache/company_revisit.jsonl as ATS research follow-ups.",
    )
    parser.add_argument(
        "--set-job-status",
        choices=VALID_JOB_TRACKING_STATUSES,
        help="Upsert a job-level tracking record in crawler_cache/job_tracking.jsonl.",
    )
    parser.add_argument(
        "--backfill-pending-review",
        action="store_true",
        help="Create pending_review tracking records for matched jobs that exist in the current snapshot but are missing from crawler_cache/job_tracking.jsonl.",
    )
    parser.add_argument(
        "--company-slug",
        help="Company slug for a job tracking update, for example 'affirm' or 'instacart'.",
    )
    parser.add_argument(
        "--job-id",
        help="Job id for a job tracking update. Supports existing Greenhouse numeric ids and Workday ids.",
    )
    parser.add_argument(
        "--review-date",
        help="Review date to store on the job tracking record in ISO format (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--application-date",
        help="Application date to store on the job tracking record in ISO format (YYYY-MM-DD). Use an empty string to clear it.",
    )
    parser.add_argument(
        "--next-action-date",
        help="Next action date to store on the job tracking record in ISO format (YYYY-MM-DD). Use an empty string to clear it.",
    )
    parser.add_argument(
        "--notes",
        help="Freeform notes to store on the job tracking record.",
    )
    parser.add_argument(
        "--match-rationale",
        help="Short rationale explaining why the job was marked with this status.",
    )
    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be at least 1.")
    if args.delay <= 0:
        parser.error("--delay must be greater than 0.")
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1.")
    if args.timeout < 1:
        parser.error("--timeout must be at least 1.")
    if args.workday_discovery_limit < 1:
        parser.error("--workday-discovery-limit must be at least 1.")
    if args.set_job_status and (not args.company_slug or not clean_display_text(str(args.job_id or ""))):
        parser.error("--set-job-status requires both --company-slug and --job-id.")
    if args.set_company_workday_board and not all(
        (
            clean_display_text(str(args.company_name or "")),
            clean_display_text(str(args.workday_tenant or "")),
            clean_display_text(str(args.workday_site_id or "")),
            clean_display_text(str(args.workday_board_url or "")),
        )
    ):
        parser.error("--set-company-workday-board requires --company-name, --workday-tenant, --workday-site-id, and --workday-board-url.")
    if not args.set_job_status and not args.set_company_workday_board and not args.backfill_pending_review and any(
        value is not None
        for value in (args.company_slug, args.job_id, args.review_date, args.application_date, args.next_action_date, args.notes, args.match_rationale)
    ):
        parser.error("Job tracking update flags require --set-job-status or --backfill-pending-review.")
    if args.backfill_pending_review and any(value is not None for value in (args.company_slug, args.job_id, args.application_date, args.next_action_date)):
        parser.error("--backfill-pending-review does not support --company-slug, --job-id, --application-date, or --next-action-date.")
    for value, flag_name in (
        (args.review_date, "--review-date"),
        (args.application_date, "--application-date"),
        (args.next_action_date, "--next-action-date"),
    ):
        if value not in (None, "") and parse_iso_date(value) is None:
            parser.error(f"{flag_name} must use YYYY-MM-DD format.")
    return args


async def run(
    args: argparse.Namespace,
) -> int:
    ensure_cache_dir()
    ensure_tracking_files()

    command_result = await handle_cli_command(args)
    if command_result is not None:
        return command_result

    search_cache = load_company_search_cache()
    non_greenhouse_cache = load_non_greenhouse_companies()

    skipped_assessments: list[CompanyAssessment] = []
    if args.company:
        selected_company_names = args.company[:args.limit]
    else:
        selected_company_names = []
        for company_name in DEFAULT_TARGET_COMPANIES:
            company_name = clean_display_text(company_name)
            if not company_name:
                continue
            company_key = company_cache_key(company_name)
            if company_key in non_greenhouse_cache:
                skipped_assessments.append(
                    CompanyAssessment(
                        name=company_name,
                        attempted_slugs=[],
                        resolved_slug=None,
                        board_url=None,
                        status="Skipped (known non-Greenhouse)",
                    )
                )
                continue
            cached_record = search_cache.get(company_key)
            if cached_record is not None:
                skipped_assessments.append(
                    build_cached_assessment(
                        company_name=company_name,
                        record=cached_record,
                        status="Skipped (already searched)",
                    )
                )
                continue
            selected_company_names.append(company_name)
            if len(selected_company_names) >= args.limit:
                break

    targets = build_target_companies(selected_company_names)
    if not targets and not skipped_assessments:
        raise CrawlError("No target companies were provided.")
    if not targets:
        print(format_results(skipped_assessments))
        return 0

    explicit_company_keys = {company_cache_key(company_name) for company_name in (args.company or [])}
    greenhouse_targets = [
        target for target in targets
        if not (
            company_cache_key(target.name) in explicit_company_keys
            and has_workday_board_hint(target.name)
        )
    ]
    workday_only_targets = [
        target for target in targets
        if company_cache_key(target.name) in explicit_company_keys and has_workday_board_hint(target.name)
    ]

    crawler = GreenhouseCrawler(
        delay_seconds=args.delay,
        concurrency=args.concurrency,
        timeout_seconds=args.timeout,
    )
    if greenhouse_targets:
        crawl_run = await crawler.crawl(greenhouse_targets)
    else:
        crawl_run = CrawlRun(assessments=[], matched_jobs=[])

    greenhouse_assessments_by_key = {
        company_cache_key(assessment.name): assessment
        for assessment in crawl_run.assessments
    }

    phenom_targets = [
        target for target, assessment in zip(greenhouse_targets, crawl_run.assessments)
        if has_phenom_search_hint(target.name) and assessment.status != "Matched jobs found"
    ]
    if phenom_targets:
        phenom_crawler = PhenomPeopleCrawler(
            delay_seconds=args.delay,
            concurrency=args.concurrency,
            timeout_seconds=args.timeout,
        )
        phenom_run = await phenom_crawler.crawl(phenom_targets)
    else:
        phenom_run = None

    phenom_assessments_by_key = {
        company_cache_key(assessment.name): assessment
        for assessment in (phenom_run.assessments if phenom_run is not None else [])
    }

    workday_targets = workday_only_targets + [
        target for target, assessment in zip(greenhouse_targets, crawl_run.assessments)
        if has_workday_board_hint(target.name)
        and phenom_assessments_by_key.get(company_cache_key(target.name), assessment).status != "Matched jobs found"
    ]
    replacement_assessments = {
        company_cache_key(assessment.name): assessment
        for assessment in crawl_run.assessments
    }
    replacement_jobs = {company_cache_key(target.name): [] for target in targets}
    for assessment in crawl_run.assessments:
        replacement_jobs[company_cache_key(assessment.name)] = list(assessment.matched_jobs)

    if phenom_run is not None:
        for assessment in phenom_run.assessments:
            company_key = company_cache_key(assessment.name)
            replacement_assessments[company_key] = assessment
            replacement_jobs[company_key] = list(assessment.matched_jobs)

    if workday_targets:
        workday_crawler = WorkdayCrawler(
            delay_seconds=args.delay,
            concurrency=args.concurrency,
            timeout_seconds=args.timeout,
        )
        workday_run = await workday_crawler.crawl(workday_targets)
        for assessment in workday_run.assessments:
            company_key = company_cache_key(assessment.name)
            replacement_assessments[company_key] = assessment
            replacement_jobs[company_key] = list(assessment.matched_jobs)
        today_iso = workday_crawler.today.isoformat()
    elif phenom_run is not None:
        today_iso = phenom_crawler.today.isoformat()
    else:
        today_iso = crawler.today.isoformat()

    final_assessments = [replacement_assessments[company_cache_key(target.name)] for target in targets]
    refreshed_company_keys = {company_cache_key(company.name) for company in targets}
    refreshed_jobs = [job for target in targets for job in replacement_jobs[company_cache_key(target.name)]]
    merged_jobs = merge_matched_jobs_snapshot(load_matched_jobs_snapshot(), refreshed_jobs, refreshed_company_keys)
    written = save_matched_jobs(merged_jobs)
    log_step(f"Wrote {written} matched jobs to {MATCHED_JOBS_PATH}")

    for assessment in final_assessments:
        search_cache[company_cache_key(assessment.name)] = build_search_record(assessment, today_iso=today_iso)
        greenhouse_assessment = greenhouse_assessments_by_key.get(company_cache_key(assessment.name))
        if greenhouse_assessment is not None and greenhouse_assessment.status == "Greenhouse board not found":
            non_greenhouse_cache[company_cache_key(greenhouse_assessment.name)] = greenhouse_assessment.name
        else:
            non_greenhouse_cache.pop(company_cache_key(assessment.name), None)

    written_search_records = save_company_search_cache(search_cache)
    written_non_greenhouse = save_non_greenhouse_companies(non_greenhouse_cache)
    synced_company_revisits = sync_non_greenhouse_company_revisits(
        search_cache=search_cache,
        non_greenhouse_cache=non_greenhouse_cache,
        today_iso=today_iso,
    )
    log_step(f"Updated {written_search_records} search-cache records in {SEARCHED_COMPANIES_PATH}")
    log_step(f"Recorded {written_non_greenhouse} non-Greenhouse companies in {NON_GREENHOUSE_COMPANIES_PATH}")
    log_step(f"Tracked {synced_company_revisits} new ATS research follow-ups in {COMPANY_REVISIT_PATH}")
    written_registry_records = sync_company_registry(
        search_cache=search_cache,
        non_greenhouse_cache=non_greenhouse_cache,
        company_revisits=load_company_revisit_records(),
        greenhouse_assessments=crawl_run.assessments,
        workday_assessments=workday_run.assessments if workday_targets else (),
        other_ats_assessments=phenom_run.assessments if phenom_run is not None else (),
    )
    log_step(f"Updated {written_registry_records} company ATS registry records in {COMPANY_REGISTRY_PATH}")

    assessments = skipped_assessments + final_assessments
    output = format_results(assessments)
    matched_jobs_section = format_matched_jobs(refreshed_jobs)
    matched_urls_section = format_matched_job_urls(refreshed_jobs)
    print(output + matched_jobs_section + matched_urls_section)
    return 0


def should_exit_after_sync(args: argparse.Namespace) -> bool:
    return args.sync_non_greenhouse_revisits and not any(
        (
            args.show_company_list,
            args.show_cache_stats,
            args.show_tracking_report,
            args.show_company_ats_report,
            args.show_intake_workday_report,
            args.set_company_workday_board,
            args.discover_workday_boards,
            args.set_job_status is not None,
            args.company,
        )
    )


async def handle_cli_command(args: argparse.Namespace) -> int | None:
    if args.sync_non_greenhouse_revisits:
        created = sync_non_greenhouse_company_revisits()
        log_step(f"Synced {created} non-Greenhouse company revisit records into {COMPANY_REVISIT_PATH}")

    if should_exit_after_sync(args):
        return 0

    if args.show_company_list:
        for company_name in DEFAULT_TARGET_COMPANIES:
            print(company_name)
        return 0

    if args.show_cache_stats:
        print(summarize_output_stats())
        return 0

    if args.show_tracking_report:
        print(format_tracking_report())
        return 0

    if args.show_company_ats_report:
        sync_company_registry()
        print(format_company_ats_report())
        return 0

    if args.show_intake_workday_report:
        sync_company_registry()
        print(format_intake_workday_report())
        return 0

    if args.set_company_workday_board:
        updated = promote_company_to_workday(
            company_name=clean_display_text(args.company_name or ""),
            tenant=clean_display_text(args.workday_tenant or ""),
            site_id=clean_display_text(args.workday_site_id or ""),
            board_url=clean_display_text(args.workday_board_url or ""),
        )
        print(json.dumps(updated, indent=2, sort_keys=True))
        return 0

    if args.discover_workday_boards:
        results = await discover_workday_boards(
            company_names=args.company,
            limit=args.workday_discovery_limit,
            delay=args.delay,
            concurrency=args.concurrency,
            timeout=args.timeout,
            apply_confirmed_results=args.apply_discovered_workday_boards,
            apply_not_found_results=args.apply_workday_not_found_results,
        )
        print(
            format_workday_discovery_report(
                results,
                applied=args.apply_discovered_workday_boards or args.apply_workday_not_found_results,
            )
        )
        return 0

    if args.set_job_status is not None:
        updated = upsert_job_tracking_record(
            company_slug=clean_display_text(args.company_slug or ""),
            greenhouse_job_id=normalize_job_id(args.job_id),
            status=args.set_job_status,
            review_date=args.review_date,
            application_date=args.application_date,
            next_action_date=args.next_action_date,
            notes=args.notes,
            match_rationale=args.match_rationale,
        )
        print(json.dumps(updated, indent=2, sort_keys=True))
        return 0

    if args.backfill_pending_review:
        created = backfill_pending_review_records(
            review_date=args.review_date,
            notes=args.notes,
            match_rationale=args.match_rationale,
        )
        print(f"Created {created} pending_review tracking records.")
        return 0

    return None


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(run(args))
    except CrawlError as exc:
        print(f"Crawl blocked: {exc}", file=sys.stderr)
        return 2
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
