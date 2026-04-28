from __future__ import annotations

import asyncio
import json
import re
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from ats_config import load_workday_board_hints
from ats_common import (
    AsyncRateLimiter,
    REMOTE_LOCATION_PATTERN,
    US_LOCATION_PATTERN,
    clean_display_text,
    company_cache_key,
    extract_canonical_url,
    extract_job_posting_json_ld,
    extract_open_graph_content,
    infer_title_matches,
    is_target_location,
    log_step,
    normalize_job_id,
    normalize_match_text,
    USER_AGENT,
)
from ats_models import CompanyAssessment, CrawlRun, JobMatchResult, MatchedJob, TargetCompany


WORKDAY_BOARD_HINTS = load_workday_board_hints(
    normalize_company_key=company_cache_key,
    normalize_text=clean_display_text,
)


def has_workday_board_hint(company_name: str) -> bool:
    return company_cache_key(company_name) in WORKDAY_BOARD_HINTS


def build_workday_jobs_url(board_url: str, tenant: str, site_id: str) -> str:
    board_match = re.match(r"https://([^/]+)/", board_url)
    host = board_match.group(1) if board_match is not None else f"{tenant}.wd1.myworkdayjobs.com"
    return f"https://{host}/wday/cxs/{quote(tenant, safe='')}/{quote(site_id, safe='')}/jobs"


def build_workday_detail_url(board_url: str, external_path: str) -> str:
    external_path = clean_display_text(external_path)
    if not external_path:
        return board_url
    if not external_path.startswith("/"):
        external_path = f"/{external_path}"
    board_prefix = board_url.rsplit("/jobs", 1)[0] if "/jobs" in board_url else board_url.rstrip("/")
    return f"{board_prefix}{external_path}"


def build_workday_details_route(board_url: str, external_path: str) -> str:
    job_slug = clean_display_text(external_path).rstrip("/").rsplit("/", 1)[-1]
    if not job_slug:
        return board_url
    return f"{board_url.rstrip('/')}/details/{job_slug}"


def build_workday_location_name(job_summary: dict, job_posting: dict) -> str:
    location_name = clean_display_text(str(job_summary.get("locationsText") or ""))
    job_location = job_posting.get("jobLocation") or {}
    address = job_location.get("address") or {}
    locality = clean_display_text(str(address.get("addressLocality") or ""))
    country = clean_display_text(str(address.get("addressCountry") or ""))
    if locality and country:
        return f"{locality}, {country}"
    if locality:
        return locality
    if location_name:
        return location_name
    if country:
        return country
    return ""


def is_target_workday_location(job_summary: dict, job_posting: dict) -> bool:
    location_name = build_workday_location_name(job_summary, job_posting)
    if is_target_location(location_name):
        return True

    remote_type = normalize_match_text(str(job_summary.get("remoteType") or ""))
    job_location_type = normalize_match_text(str(job_posting.get("jobLocationType") or ""))
    applicant_location = job_posting.get("applicantLocationRequirements") or {}
    applicant_country = clean_display_text(str(applicant_location.get("name") or ""))
    job_location = job_posting.get("jobLocation") or {}
    address = job_location.get("address") or {}
    address_country = clean_display_text(str(address.get("addressCountry") or ""))
    is_remote = bool(REMOTE_LOCATION_PATTERN.search(remote_type)) or job_location_type == "telecommute"
    is_us = bool(US_LOCATION_PATTERN.search(applicant_country)) or bool(US_LOCATION_PATTERN.search(address_country))
    return is_remote and is_us


class WorkdayCrawler:
    def __init__(self, *, delay_seconds: float, concurrency: int, timeout_seconds: int) -> None:
        self.rate_limiter = AsyncRateLimiter(delay_seconds)
        self.semaphore = asyncio.Semaphore(concurrency)
        self.timeout_seconds = timeout_seconds
        self.today = date.today()

    async def crawl(self, companies: list[TargetCompany]) -> CrawlRun:
        log_step(f"Starting Workday crawl for {len(companies)} target companies")
        assessments = await asyncio.gather(*(self._crawl_company(company) for company in companies))
        matched_jobs = [job for assessment in assessments for job in assessment.matched_jobs]
        return CrawlRun(assessments=assessments, matched_jobs=matched_jobs)

    async def _crawl_company(self, company: TargetCompany) -> CompanyAssessment:
        hint = WORKDAY_BOARD_HINTS.get(company_cache_key(company.name))
        if hint is None:
            return CompanyAssessment(company.name, [], None, None, "Workday board not configured", source="workday")

        tenant = hint["tenant"]
        site_id = hint["site_id"]
        board_url = hint["board_url"]
        api_url = build_workday_jobs_url(board_url, tenant, site_id)
        try:
            job_summaries = await self._fetch_all_job_summaries(api_url)
        except (HTTPError, URLError, TimeoutError) as exc:
            return CompanyAssessment(company.name, [board_url], f"{tenant}/{site_id}", board_url, f"Network error: {exc}", source="workday")

        if not job_summaries:
            return CompanyAssessment(company.name, [board_url], f"{tenant}/{site_id}", board_url, "No open jobs", source="workday")

        detailed_jobs = await self._fetch_job_details(company_name=company.name, board_url=board_url, jobs=job_summaries)
        matched_jobs = [result.matched_job for result in detailed_jobs if result.matched_job is not None]
        title_matches = any(result.title_matched for result in detailed_jobs)
        location_matches = any(result.location_matched for result in detailed_jobs)
        status = "Matched jobs found" if matched_jobs else "No jobs in Austin/US-remote" if title_matches and not location_matches else "No matching job titles"
        return CompanyAssessment(company.name, [board_url], f"{tenant}/{site_id}", board_url, status, source="workday", jobs_seen=len(job_summaries), matched_jobs=matched_jobs)

    async def _fetch_all_job_summaries(self, api_url: str) -> list[dict]:
        offset = 0
        limit = 20
        job_summaries: list[dict] = []
        while True:
            payload = await self._post_json(api_url, {"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""})
            page = payload.get("jobPostings") or []
            if not isinstance(page, list):
                break
            job_summaries.extend(job for job in page if isinstance(job, dict))
            if len(page) < limit:
                break
            offset += limit
        return job_summaries

    async def _fetch_job_details(self, *, company_name: str, board_url: str, jobs: list[dict]) -> list[JobMatchResult]:
        return await asyncio.gather(
            *(self._fetch_and_match_job_detail(company_name=company_name, board_url=board_url, job_summary=job_summary) for job_summary in jobs)
        )

    async def _fetch_and_match_job_detail(self, *, company_name: str, board_url: str, job_summary: dict) -> JobMatchResult:
        title = clean_display_text(str(job_summary.get("title") or ""))
        matched_keywords, matched_role_families = infer_title_matches(title)
        if not matched_keywords:
            return JobMatchResult(matched_job=None)

        external_path = clean_display_text(str(job_summary.get("externalPath") or ""))
        detail_url = build_workday_detail_url(board_url, external_path)
        try:
            detail_html = await self._fetch_text(detail_url)
        except (HTTPError, URLError, TimeoutError) as exc:
            fallback_detail_url = build_workday_details_route(board_url, external_path)
            if fallback_detail_url == detail_url:
                log_step(f"{company_name}: failed to fetch Workday detail for {detail_url}: {exc}")
                return JobMatchResult(matched_job=None, title_matched=True)
            try:
                detail_html = await self._fetch_text(fallback_detail_url)
                detail_url = fallback_detail_url
            except (HTTPError, URLError, TimeoutError) as fallback_exc:
                log_step(
                    f"{company_name}: failed to fetch Workday detail for {detail_url} and fallback {fallback_detail_url}: {fallback_exc}"
                )
                return JobMatchResult(matched_job=None, title_matched=True)

        job_posting = extract_job_posting_json_ld(detail_html)
        if not is_target_workday_location(job_summary, job_posting):
            return JobMatchResult(matched_job=None, title_matched=True)

        identifier = job_posting.get("identifier") or {}
        job_id = normalize_job_id(identifier.get("value") if isinstance(identifier, dict) else "")
        if not job_id:
            bullet_fields = job_summary.get("bulletFields") or []
            if isinstance(bullet_fields, list) and bullet_fields:
                job_id = normalize_job_id(bullet_fields[0])
        if not job_id:
            job_id = normalize_job_id(detail_url.rsplit("/", 1)[-1])

        description = clean_display_text(str(job_posting.get("description") or "")) or extract_open_graph_content(detail_html, "og:description")
        location_name = build_workday_location_name(job_summary, job_posting)
        return JobMatchResult(
            matched_job=MatchedJob(
                company_name=company_name,
                company_slug=company_cache_key(company_name),
                careers_url=board_url,
                greenhouse_job_id=job_id,
                job_title=title or clean_display_text(str(job_posting.get("title") or "Unknown Role")),
                job_url=extract_canonical_url(detail_html) or detail_url,
                job_location=location_name,
                matched_keywords=matched_keywords,
                matched_role_families=matched_role_families,
                found_date=self.today.isoformat(),
                job_description=description,
            ),
            title_matched=True,
            location_matched=True,
        )

    async def _fetch_text(self, url: str) -> str:
        async with self.semaphore:
            await self.rate_limiter.wait()
            return await asyncio.to_thread(self._fetch_text_blocking, url)

    def _fetch_text_blocking(self, url: str) -> str:
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
        with urlopen(request, timeout=self.timeout_seconds) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise HTTPError(url, status, f"Unexpected status {status}", hdrs=None, fp=None)
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")

    async def _post_json(self, url: str, payload: dict) -> dict:
        async with self.semaphore:
            await self.rate_limiter.wait()
            return await asyncio.to_thread(self._post_json_blocking, url, payload)

    def _post_json_blocking(self, url: str, payload: dict) -> dict:
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json", "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise HTTPError(url, status, f"Unexpected status {status}", hdrs=None, fp=None)
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset, errors="replace"))