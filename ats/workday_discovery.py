from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .common import AsyncRateLimiter, clean_display_text, company_cache_key, dedupe_preserve_order, log_step, USER_AGENT
from .workday import build_workday_jobs_url


WORKDAY_HOST_PREFIXES = tuple(f"wd{index}" for index in range(1, 6))
COMMON_SITE_IDS = ("jobs", "Jobs", "careers", "Careers", "Search", "external", "External")
COMMON_COMPANY_SUFFIXES = {
    "co",
    "company",
    "corp",
    "corporation",
    "inc",
    "llc",
    "service",
    "services",
    "enterprise",
    "enterprises",
    "group",
    "holding",
    "holdings",
    "management",
    "technology",
    "technologies",
}
CONNECTIVITY_PROBE = {
    "board_url": "https://3m.wd1.myworkdayjobs.com/en-US/Search",
    "tenant": "3m",
    "site_id": "Search",
}


def build_workday_tenant_candidates(company_name: str) -> list[str]:
    normalized = company_cache_key(company_name)
    tokens = _trim_discovery_tokens(re.findall(r"[a-z0-9]+", normalized))
    if not tokens:
        return []

    compact = "".join(tokens)
    candidates = [compact]
    if len(tokens) > 1:
        candidates.extend([tokens[0], tokens[-1], "".join(tokens[:2])])
    return [candidate for candidate in dedupe_preserve_order(clean_display_text(value) for value in candidates) if candidate]


def build_workday_site_candidates(company_name: str) -> list[str]:
    candidates = list(COMMON_SITE_IDS)
    normalized_tokens = re.findall(r"[a-z0-9]+", company_cache_key(company_name))
    token_sets = [normalized_tokens, _trim_discovery_tokens(normalized_tokens)]
    for tokens in token_sets:
        if not tokens:
            continue
        pascal_name = "".join(token[:1].upper() + token[1:] for token in tokens)
        compact = "".join(tokens)
        candidates.extend([f"{pascal_name}Careers", f"{pascal_name}Jobs", f"{compact}Careers", f"{compact}Jobs"])

    return [candidate for candidate in dedupe_preserve_order(clean_display_text(value) for value in candidates) if candidate]


def _trim_discovery_tokens(tokens: list[str]) -> list[str]:
    trimmed = [token for token in tokens if not (len(token) == 1 and token.isalpha())]
    while trimmed and trimmed[-1] in COMMON_COMPANY_SUFFIXES:
        trimmed.pop()
    return trimmed


def build_workday_board_url_candidates(company_name: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for tenant in build_workday_tenant_candidates(company_name):
        for host_prefix in WORKDAY_HOST_PREFIXES:
            host = f"{tenant}.{host_prefix}.myworkdayjobs.com"
            for site_id in build_workday_site_candidates(company_name):
                candidates.append(
                    {
                        "tenant": tenant,
                        "site_id": site_id,
                        "board_url": f"https://{host}/en-US/{site_id}",
                    }
                )
                candidates.append(
                    {
                        "tenant": tenant,
                        "site_id": site_id,
                        "board_url": f"https://{host}/en-US/{site_id}/jobs",
                    }
                )
                candidates.append(
                    {
                        "tenant": tenant,
                        "site_id": site_id,
                        "board_url": f"https://{host}/{site_id}",
                    }
                )

    seen: set[tuple[str, str, str]] = set()
    ordered: list[dict[str, str]] = []
    for candidate in candidates:
        key = (candidate["tenant"], candidate["site_id"], candidate["board_url"])
        if key in seen:
            continue
        seen.add(key)
        ordered.append(candidate)
    return ordered


def build_workday_probe_key(candidate: dict[str, str]) -> tuple[str, str, str]:
    return (urlsplit(candidate["board_url"]).netloc, candidate["tenant"], candidate["site_id"])


class WorkdayBoardDiscoverer:
    def __init__(self, *, delay_seconds: float, concurrency: int, timeout_seconds: int) -> None:
        self.rate_limiter = AsyncRateLimiter(delay_seconds)
        self.semaphore = asyncio.Semaphore(concurrency)
        self.timeout_seconds = timeout_seconds

    async def discover_company(self, company_name: str) -> dict:
        grouped_candidates: dict[tuple[str, str, str], list[dict[str, str]]] = {}
        ordered_keys: list[tuple[str, str, str]] = []
        for candidate in build_workday_board_url_candidates(company_name):
            probe_key = build_workday_probe_key(candidate)
            if probe_key not in grouped_candidates:
                grouped_candidates[probe_key] = []
                ordered_keys.append(probe_key)
            grouped_candidates[probe_key].append(candidate)

        for probe_key in ordered_keys:
            candidate_group = grouped_candidates[probe_key]
            candidate = candidate_group[0]
            try:
                payload = await self._probe_jobs_api(
                    board_url=candidate["board_url"],
                    tenant=candidate["tenant"],
                    site_id=candidate["site_id"],
                )
            except (HTTPError, URLError, TimeoutError):
                continue
            except json.JSONDecodeError as exc:
                log_step(
                    f"{company_name}: skipping malformed Workday probe response for {candidate['tenant']}/{candidate['site_id']}: {exc}"
                )
                continue
            except Exception as exc:  # pragma: no cover - defensive command path
                return {
                    "company_name": company_name,
                    "status": "error",
                    "detail": str(exc),
                }

            job_postings = payload.get("jobPostings")
            total_jobs = payload.get("total")
            if isinstance(job_postings, list) or isinstance(total_jobs, int):
                resolved_board_url = await self._resolve_board_url(candidate_group)
                detail = f"Discovered Workday board; jobs={total_jobs if isinstance(total_jobs, int) else len(job_postings or [])}"
                log_step(f"{company_name}: confirmed Workday board {resolved_board_url}")
                return {
                    "company_name": company_name,
                    "status": "confirmed",
                    "detail": detail,
                    "board_url": resolved_board_url,
                    "tenant": candidate["tenant"],
                    "site_id": candidate["site_id"],
                }

        return {
            "company_name": company_name,
            "status": "not_found",
            "detail": "No supported Workday board pattern responded successfully.",
        }

    async def discover_companies(self, company_names: list[str]) -> list[dict]:
        connectivity_error = await self._check_workday_connectivity()
        if connectivity_error:
            return [
                {
                    "company_name": company_name,
                    "status": "needs_retry",
                    "detail": f"Workday connectivity probe failed: {connectivity_error}",
                }
                for company_name in company_names
            ]
        return await asyncio.gather(*(self.discover_company(company_name) for company_name in company_names))

    async def _check_workday_connectivity(self) -> str:
        try:
            await self._probe_jobs_api(
                board_url=CONNECTIVITY_PROBE["board_url"],
                tenant=CONNECTIVITY_PROBE["tenant"],
                site_id=CONNECTIVITY_PROBE["site_id"],
            )
        except HTTPError:
            return ""
        except (URLError, TimeoutError) as exc:
            return str(exc)
        return ""

    async def _probe_jobs_api(self, *, board_url: str, tenant: str, site_id: str) -> dict:
        async with self.semaphore:
            await self.rate_limiter.wait()
            return await asyncio.to_thread(self._probe_jobs_api_blocking, board_url, tenant, site_id)

    async def _resolve_board_url(self, candidates: list[dict[str, str]]) -> str:
        for candidate in candidates:
            try:
                return await self._probe_board_url(candidate["board_url"])
            except (HTTPError, URLError, TimeoutError):
                continue
        return candidates[0]["board_url"]

    async def _probe_board_url(self, board_url: str) -> str:
        async with self.semaphore:
            await self.rate_limiter.wait()
            return await asyncio.to_thread(self._probe_board_url_blocking, board_url)

    def _probe_jobs_api_blocking(self, board_url: str, tenant: str, site_id: str) -> dict:
        api_url = build_workday_jobs_url(board_url, tenant, site_id)
        request = Request(
            api_url,
            data=json.dumps({"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""}).encode("utf-8"),
            method="POST",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json", "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise HTTPError(api_url, status, f"Unexpected status {status}", hdrs=None, fp=None)
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset, errors="replace"))

    def _probe_board_url_blocking(self, board_url: str) -> str:
        request = Request(
            board_url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            status = getattr(response, "status", 200)
            if status >= 400:
                raise HTTPError(board_url, status, f"Unexpected status {status}", hdrs=None, fp=None)
            return response.geturl() or board_url
