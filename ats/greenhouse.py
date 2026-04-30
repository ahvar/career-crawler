from __future__ import annotations

import asyncio
import json
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .common import AsyncRateLimiter, html_to_text, infer_title_matches, is_target_location, log_step, normalize_job_id, USER_AGENT, clean_display_text
from .models import CompanyAssessment, CrawlRun, JobMatchResult, MatchedJob, TargetCompany


GREENHOUSE_API_ROOT = "https://boards-api.greenhouse.io/v1/boards"
GREENHOUSE_BOARD_ROOT = "https://boards.greenhouse.io"


def greenhouse_jobs_url(slug: str) -> str:
    return f"{GREENHOUSE_API_ROOT}/{quote(slug, safe='')}/jobs"


def greenhouse_job_detail_url(slug: str, job_id: str) -> str:
    return f"{GREENHOUSE_API_ROOT}/{quote(slug, safe='')}/jobs/{quote(job_id, safe='')}"


def greenhouse_board_url(slug: str) -> str:
    return f"{GREENHOUSE_BOARD_ROOT}/{quote(slug, safe='')}"


class GreenhouseCrawler:
    def __init__(self, *, delay_seconds: float, concurrency: int, timeout_seconds: int) -> None:
        self.rate_limiter = AsyncRateLimiter(delay_seconds)
        self.semaphore = asyncio.Semaphore(concurrency)
        self.timeout_seconds = timeout_seconds
        self.today = date.today()

    async def crawl(self, companies: list[TargetCompany]) -> CrawlRun:
        log_step(f"Starting Greenhouse crawl for {len(companies)} target companies")
        assessments = await asyncio.gather(*(self._crawl_company(company) for company in companies))
        matched_jobs = [job for assessment in assessments for job in assessment.matched_jobs]
        return CrawlRun(assessments=assessments, matched_jobs=matched_jobs)

    async def _crawl_company(self, company: TargetCompany) -> CompanyAssessment:
        attempted_slugs = list(company.slug_candidates)
        if not attempted_slugs:
            return CompanyAssessment(
                name=company.name,
                attempted_slugs=[],
                resolved_slug=None,
                board_url=None,
                status="No slug candidates",
            )

        log_step(f"{company.name}: trying Greenhouse slugs {', '.join(attempted_slugs)}")
        saw_empty_board = False
        for slug in attempted_slugs:
            try:
                jobs_payload = await self._fetch_json(greenhouse_jobs_url(slug))
            except HTTPError as exc:
                if exc.code == 404:
                    log_step(f"{company.name}: slug {slug} returned 404")
                    continue
                return CompanyAssessment(company.name, attempted_slugs, slug, greenhouse_board_url(slug), f"HTTP {exc.code}")
            except (URLError, TimeoutError) as exc:
                return CompanyAssessment(company.name, attempted_slugs, slug, greenhouse_board_url(slug), f"Network error: {exc}")

            job_summaries = jobs_payload.get("jobs") or []
            if not job_summaries:
                saw_empty_board = True
                log_step(f"{company.name}: slug {slug} has no open jobs")
                continue

            log_step(f"{company.name}: resolved board {slug} with {len(job_summaries)} open jobs")
            detailed_jobs = await self._fetch_job_details(company_name=company.name, slug=slug, jobs=job_summaries)
            matched_jobs = [result.matched_job for result in detailed_jobs if result.matched_job is not None]
            title_matches = any(result.title_matched for result in detailed_jobs)
            location_matches = any(result.location_matched for result in detailed_jobs)
            status = "Matched jobs found" if matched_jobs else "No jobs in Austin/US-remote" if title_matches and not location_matches else "No matching job titles"
            return CompanyAssessment(company.name, attempted_slugs, slug, greenhouse_board_url(slug), status, jobs_seen=len(job_summaries), matched_jobs=matched_jobs)

        final_status = "No open jobs" if saw_empty_board else "Greenhouse board not found"
        return CompanyAssessment(company.name, attempted_slugs, None, None, final_status)

    async def _fetch_job_details(self, *, company_name: str, slug: str, jobs: list[dict]) -> list[JobMatchResult]:
        return await asyncio.gather(
            *(self._fetch_and_match_job_detail(company_name=company_name, slug=slug, job_summary=job_summary) for job_summary in jobs)
        )

    async def _fetch_and_match_job_detail(self, *, company_name: str, slug: str, job_summary: dict) -> JobMatchResult:
        job_id = normalize_job_id(job_summary.get("id"))
        if not job_id:
            return JobMatchResult(matched_job=None)

        title = clean_display_text(str(job_summary.get("title") or ""))
        matched_keywords, matched_role_families = infer_title_matches(title)
        if not matched_keywords:
            return JobMatchResult(matched_job=None)

        try:
            detail_payload = await self._fetch_json(greenhouse_job_detail_url(slug, job_id))
        except (HTTPError, URLError, TimeoutError) as exc:
            log_step(f"{company_name}: failed to fetch detail for job {job_id}: {exc}")
            return JobMatchResult(matched_job=None, title_matched=True)

        location = job_summary.get("location") or detail_payload.get("location") or {}
        location_name = clean_display_text(str(location.get("name") or ""))
        if not is_target_location(location_name):
            return JobMatchResult(matched_job=None, title_matched=True)

        return JobMatchResult(
            matched_job=MatchedJob(
                company_name=company_name,
                company_slug=slug,
                careers_url=greenhouse_board_url(slug),
                greenhouse_job_id=job_id,
                job_title=title or "Unknown Role",
                job_url=str(detail_payload.get("absolute_url") or job_summary.get("absolute_url") or greenhouse_board_url(slug)),
                job_location=location_name,
                matched_keywords=matched_keywords,
                matched_role_families=matched_role_families,
                found_date=self.today.isoformat(),
                job_description=html_to_text(str(detail_payload.get("content") or "")),
            ),
            title_matched=True,
            location_matched=True,
        )

    async def _fetch_json(self, url: str) -> dict:
        async with self.semaphore:
            await self.rate_limiter.wait()
            return await asyncio.to_thread(self._fetch_json_blocking, url)

    def _fetch_json_blocking(self, url: str) -> dict:
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urlopen(request, timeout=self.timeout_seconds) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise HTTPError(url, status, f"Unexpected status {status}", hdrs=None, fp=None)
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset, errors="replace"))