from __future__ import annotations

import asyncio
import json
import re
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .common import (
    AsyncRateLimiter,
    USER_AGENT,
    clean_display_text,
    company_cache_key,
    extract_canonical_url,
    extract_job_posting_json_ld,
    extract_open_graph_content,
    html_to_text,
    infer_title_matches,
    is_target_location,
    log_step,
    normalize_job_id,
)
from .config import load_phenom_search_hints
from .models import CompanyAssessment, CrawlRun, JobMatchResult, MatchedJob, TargetCompany


PHENOM_SEARCH_HINTS = load_phenom_search_hints(
    normalize_company_key=company_cache_key,
    normalize_text=clean_display_text,
)

PHENOM_DDO_PATTERN = re.compile(r"phApp\.ddo\s*=\s*(\{.*?\})\s*;\s*phApp\.", re.DOTALL)
ATTRAX_TILE_PATTERN = re.compile(
    r'<div class="attrax-vacancy-tile\b[^>]*data-jobid="(?P<data_jobid>[^"]+)"[^>]*>(?P<body>.*?)<div class="attrax-vacancy-tile__buttons\b',
    re.DOTALL,
)
ATTRAX_TITLE_PATTERN = re.compile(
    r'<a[^>]*class="attrax-vacancy-tile__title[^"]*"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.DOTALL,
)
ATTRAX_ITEM_VALUE_PATTERN = r'<div class="attrax-vacancy-tile__{field}[^"]*"[^>]*>.*?<p class="attrax-vacancy-tile__item-value">\s*(?P<value>.*?)\s*</p>'
ATTRAX_RESULT_COUNT_PATTERN = re.compile(r'(\d+)\s+result\(s\)', re.IGNORECASE)


def has_phenom_search_hint(company_name: str) -> bool:
    return company_cache_key(company_name) in PHENOM_SEARCH_HINTS


def build_phenom_search_results_url(search_results_url: str, offset: int) -> str:
    if offset <= 0:
        return search_results_url
    parts = urlsplit(search_results_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["from"] = str(offset)
    query["s"] = query.get("s") or "1"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def build_phenom_job_url(search_results_url: str, job_id: str, title: str) -> str:
    parts = urlsplit(search_results_url)
    title_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    path_prefix = parts.path.rstrip("/").rsplit("/search-results", 1)[0]
    return urlunsplit((parts.scheme, parts.netloc, f"{path_prefix}/job/{quote(job_id, safe='')}/{quote(title_slug, safe='-')}", "", ""))


def build_attrax_search_results_url(search_results_url: str, page_number: int) -> str:
    if page_number <= 1:
        return search_results_url
    parts = urlsplit(search_results_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["page"] = str(page_number)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def extract_phenom_ddo(html_text: str) -> dict:
    match = PHENOM_DDO_PATTERN.search(html_text)
    if match is None:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}


def extract_phenom_job_description(html_text: str, title: str) -> str:
    job_posting = extract_job_posting_json_ld(html_text)
    if isinstance(job_posting, dict):
        description = clean_display_text(str(job_posting.get("description") or ""))
        if description:
            return description

    ddo = extract_phenom_ddo(html_text)
    job_data = (ddo.get("data") or {}).get("job") or {}
    for key in ("description", "jobDescription", "formattedDescription", "descriptionTeaser"):
        description = clean_display_text(str(job_data.get(key) or ""))
        if description:
            return description

    page_text = html_to_text(html_text)
    if page_text:
        pattern = re.compile(
            rf"{re.escape(clean_display_text(title))}(.*?)(?:Get notified for similar jobs\.|Share this Opportunity|Stay in the loop\.)",
            re.IGNORECASE,
        )
        match = pattern.search(page_text)
        if match is not None:
            description = clean_display_text(match.group(1))
            if description:
                return description

    return extract_open_graph_content(html_text, "og:description")


def extract_phenom_listing_payload(html_text: str) -> tuple[list[dict], int, int]:
    ddo = extract_phenom_ddo(html_text)
    eager = ddo.get("eagerLoadRefineSearch") or {}
    data = eager.get("data") or {}
    jobs = [job for job in data.get("jobs") or [] if isinstance(job, dict)]
    total_hits = eager.get("totalHits")
    if not isinstance(total_hits, int):
        total_hits = len(jobs)
    page_size = (ddo.get("siteConfig") or {}).get("data", {}).get("size")
    if not isinstance(page_size, int):
        try:
            page_size = int(page_size)
        except (TypeError, ValueError):
            page_size = len(jobs) or 10
    return jobs, total_hits, page_size


def extract_attrax_value(card_html: str, field: str) -> str:
    match = re.search(ATTRAX_ITEM_VALUE_PATTERN.format(field=re.escape(field)), card_html, re.DOTALL)
    if match is None:
        return ""
    return clean_display_text(html_to_text(match.group("value")))


def extract_attrax_listing_payload(html_text: str, search_results_url: str) -> tuple[list[dict], int, int]:
    jobs: list[dict] = []
    for match in ATTRAX_TILE_PATTERN.finditer(html_text):
        body = match.group("body")
        title_match = ATTRAX_TITLE_PATTERN.search(body)
        if title_match is None:
            continue
        href = clean_display_text(title_match.group("href"))
        title = clean_display_text(html_to_text(title_match.group("title")))
        if not href or not title:
            continue
        jobs.append(
            {
                "title": title,
                "jobId": clean_display_text(match.group("data_jobid")),
                "reqId": extract_attrax_value(body, "externalreference"),
                "location": extract_attrax_value(body, "location-freetext") or extract_attrax_value(body, "option-location"),
                "workLocationType": extract_attrax_value(body, "option-work-location-type"),
                "jobUrl": urljoin(search_results_url, href),
            }
        )

    total_hits_match = ATTRAX_RESULT_COUNT_PATTERN.search(html_to_text(html_text))
    total_hits = int(total_hits_match.group(1)) if total_hits_match is not None else len(jobs)
    page_size = len(jobs) or 12
    return jobs, total_hits, page_size


def extract_phenom_target_location(job_summary: dict) -> str:
    multi_location = job_summary.get("multi_location") or []
    if isinstance(multi_location, list):
        for location in multi_location:
            cleaned_location = clean_display_text(str(location or ""))
            if is_target_location(cleaned_location):
                return cleaned_location

    for key in ("location", "cityStateCountry", "cityState", "address"):
        cleaned_location = clean_display_text(str(job_summary.get(key) or ""))
        if is_target_location(cleaned_location):
            return cleaned_location

    work_location_type = clean_display_text(str(job_summary.get("workLocationType") or ""))
    location = clean_display_text(str(job_summary.get("location") or ""))
    if re.search(r"\bremote\b", work_location_type, re.IGNORECASE):
        combined_location = clean_display_text(f"Remote, {location}" if location else "Remote, United States")
        if is_target_location(combined_location):
            return combined_location
    return ""


class PhenomPeopleCrawler:
    def __init__(self, *, delay_seconds: float, concurrency: int, timeout_seconds: int) -> None:
        self.rate_limiter = AsyncRateLimiter(delay_seconds)
        self.semaphore = asyncio.Semaphore(concurrency)
        self.timeout_seconds = timeout_seconds
        self.today = date.today()

    async def crawl(self, companies: list[TargetCompany]) -> CrawlRun:
        log_step(f"Starting Phenom crawl for {len(companies)} target companies")
        assessments = await asyncio.gather(*(self._crawl_company(company) for company in companies))
        matched_jobs = [job for assessment in assessments for job in assessment.matched_jobs]
        return CrawlRun(assessments=assessments, matched_jobs=matched_jobs)

    async def _crawl_company(self, company: TargetCompany) -> CompanyAssessment:
        hint = PHENOM_SEARCH_HINTS.get(company_cache_key(company.name))
        if hint is None:
            return CompanyAssessment(company.name, [], None, None, "Phenom board not configured", source="phenom")

        search_results_url = hint["search_results_url"]
        listing_mode = hint.get("listing_mode") or "phenom"
        try:
            jobs, total_hits, page_size = await self._fetch_listing_page(search_results_url, listing_mode=listing_mode)
        except (HTTPError, URLError, TimeoutError) as exc:
            return CompanyAssessment(company.name, [search_results_url], None, search_results_url, f"Network error: {exc}", source="phenom")

        if not jobs:
            return CompanyAssessment(company.name, [search_results_url], "search-results", search_results_url, "No open jobs", source="phenom")

        all_jobs = list(jobs)
        for offset in range(page_size, total_hits, page_size):
            page_url = self._build_listing_page_url(search_results_url, listing_mode=listing_mode, offset=offset, page_size=page_size)
            page_jobs, _, _ = await self._fetch_listing_page(page_url, listing_mode=listing_mode)
            if not page_jobs:
                break
            all_jobs.extend(page_jobs)

        detailed_jobs = await self._fetch_job_details(company_name=company.name, search_results_url=search_results_url, jobs=all_jobs)
        matched_jobs = [result.matched_job for result in detailed_jobs if result.matched_job is not None]
        title_matches = any(result.title_matched for result in detailed_jobs)
        location_matches = any(result.location_matched for result in detailed_jobs)
        status = "Matched jobs found" if matched_jobs else "No jobs in Austin/US-remote" if title_matches and not location_matches else "No matching job titles"
        return CompanyAssessment(
            company.name,
            [search_results_url],
            "search-results",
            search_results_url,
            status,
            source="phenom",
            jobs_seen=len(all_jobs),
            matched_jobs=matched_jobs,
        )

    async def _fetch_job_details(self, *, company_name: str, search_results_url: str, jobs: list[dict]) -> list[JobMatchResult]:
        return await asyncio.gather(
            *(self._fetch_and_match_job_detail(company_name=company_name, search_results_url=search_results_url, job_summary=job_summary) for job_summary in jobs)
        )

    async def _fetch_and_match_job_detail(self, *, company_name: str, search_results_url: str, job_summary: dict) -> JobMatchResult:
        title = clean_display_text(str(job_summary.get("title") or ""))
        matched_keywords, matched_role_families = infer_title_matches(title)
        if not matched_keywords:
            return JobMatchResult(matched_job=None)

        target_location = extract_phenom_target_location(job_summary)
        if not target_location:
            return JobMatchResult(matched_job=None, title_matched=True)

        job_id = normalize_job_id(job_summary.get("jobId") or job_summary.get("reqId"))
        if not job_id:
            return JobMatchResult(matched_job=None, title_matched=True, location_matched=True)

        detail_url = clean_display_text(str(job_summary.get("jobUrl") or "")) or build_phenom_job_url(search_results_url, job_id, title)
        try:
            detail_html = await self._fetch_text(detail_url)
        except (HTTPError, URLError, TimeoutError) as exc:
            log_step(f"{company_name}: failed to fetch Phenom detail for {job_id}: {exc}")
            return JobMatchResult(matched_job=None, title_matched=True, location_matched=True)

        return JobMatchResult(
            matched_job=MatchedJob(
                company_name=company_name,
                company_slug=company_cache_key(company_name),
                careers_url=search_results_url,
                greenhouse_job_id=job_id,
                job_title=title or "Unknown Role",
                job_url=extract_canonical_url(detail_html) or detail_url,
                job_location=target_location,
                matched_keywords=matched_keywords,
                matched_role_families=matched_role_families,
                found_date=self.today.isoformat(),
                job_description=extract_phenom_job_description(detail_html, title),
            ),
            title_matched=True,
            location_matched=True,
        )

    def _build_listing_page_url(self, search_results_url: str, *, listing_mode: str, offset: int, page_size: int) -> str:
        if listing_mode == "attrax_html":
            return build_attrax_search_results_url(search_results_url, (offset // page_size) + 1)
        return build_phenom_search_results_url(search_results_url, offset)

    async def _fetch_listing_page(self, url: str, *, listing_mode: str) -> tuple[list[dict], int, int]:
        html_text = await self._fetch_text(url)
        if listing_mode == "attrax_html":
            return extract_attrax_listing_payload(html_text, url)
        return extract_phenom_listing_payload(html_text)

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