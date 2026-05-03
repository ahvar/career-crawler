from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, quote, urlparse, urlunsplit
from urllib.request import Request, urlopen
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Config
from ats.common import extract_canonical_url, extract_job_posting_json_ld, extract_open_graph_content


CRAWLER_CACHE_DIR = ROOT / "crawler_cache"
MATCHED_JOBS_PATH = CRAWLER_CACHE_DIR / "matched_jobs.jsonl"
USER_AGENT = Config.USER_AGENT or "application-material-generator/0.1"
DEFAULT_TIMEOUT_SECONDS = 30


class HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = clean_display_text(data)
        if text:
            self._parts.append(text)

    @property
    def text(self) -> str:
        return " ".join(self._parts)


@dataclass(frozen=True)
class JobDetails:
    source_url: str
    normalized_source_url: str
    company_slug: str
    company_name: str
    job_id: str
    title: str
    location: str
    description: str
    absolute_url: str


def clean_display_text(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


def html_to_text(html: str | None) -> str:
    if not html:
        return ""
    parser = HTMLTextExtractor()
    parser.feed(html)
    return parser.text


def fetch_url(url: str, *, accept: str = "text/html,application/xhtml+xml") -> tuple[str, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
        final_url = response.geturl()
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace"), final_url


def fetch_json(url: str) -> dict[str, Any]:
    body, _ = fetch_url(url, accept="application/json")
    return json.loads(body)


def parse_greenhouse_identifiers(url: str) -> tuple[str, int] | None:
    parsed = urlparse(url)

    direct_match = re.match(r"^/([^/]+)/jobs/(\d+)", parsed.path)
    if parsed.netloc.endswith("job-boards.greenhouse.io") and direct_match:
        return direct_match.group(1), int(direct_match.group(2))

    query = parse_qs(parsed.query)
    board = query.get("for", [None])[0]
    token = query.get("token", [None])[0]
    if board and token and token.isdigit():
        return board, int(token)

    return None


def infer_board_slug_from_host(url: str) -> str | None:
    parsed = urlparse(url)
    host_parts = [part for part in parsed.netloc.lower().split(".") if part and part != "www"]
    if not host_parts:
        return None
    if host_parts[0] in {"careers", "jobs"} and len(host_parts) > 1:
        return host_parts[1]
    return host_parts[0]


def resolve_greenhouse_job(url: str) -> tuple[str, int, str]:
    direct = parse_greenhouse_identifiers(url)
    if direct is not None:
        board, job_id = direct
        return board, job_id, url

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query_id = query.get("id", [None])[0] or query.get("gh_jid", [None])[0]
    inferred_board = infer_board_slug_from_host(url)
    if inferred_board and query_id and query_id.isdigit():
        return inferred_board, int(query_id), url

    body, final_url = fetch_url(url)
    redirected = parse_greenhouse_identifiers(final_url)
    if redirected is not None:
        board, job_id = redirected
        return board, job_id, final_url

    embedded = re.search(r"embed/job_app\?for=([a-z0-9_-]+)&token=(\d+)", body)
    if embedded is not None:
        return embedded.group(1), int(embedded.group(2)), final_url

    raise ValueError(f"Unsupported or unrecognized job URL: {url}")


def greenhouse_job_detail_url(board: str, job_id: int) -> str:
    return f"https://boards-api.greenhouse.io/v1/boards/{quote(board)}/jobs/{job_id}"


def title_case_from_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in re.split(r"[-_]+", slug) if part)


def is_workday_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host.endswith("myworkdayjobs.com") or host.endswith("workdayjobs.com")


def workday_job_id_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    last_segment = path.rsplit("/", 1)[-1]
    match = re.search(r"_([A-Za-z0-9-]+)$", last_segment)
    return match.group(1) if match is not None else ""


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def normalize_snapshot_url(url: str) -> str:
    stripped = url.strip()
    parsed = urlparse(stripped)
    if not parsed.scheme or not parsed.netloc:
        return stripped.rstrip("/")
    if is_workday_url(stripped):
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", ""))
    return stripped.rstrip("/")


def snapshot_job_details_by_url(source_url: str, *, require_description: bool = True) -> JobDetails | None:
    if not MATCHED_JOBS_PATH.exists():
        return None

    normalized_source_url = normalize_snapshot_url(source_url)
    for row in load_jsonl(MATCHED_JOBS_PATH):
        row_url = normalize_snapshot_url(str(row.get("job_url") or ""))
        if row_url != normalized_source_url:
            continue

        company_slug = str(row.get("company_slug") or "")
        company_name = clean_display_text(str(row.get("company_name") or title_case_from_slug(company_slug)))
        title = clean_display_text(str(row.get("job_title") or "Untitled Role"))
        location = clean_display_text(str(row.get("job_location") or ""))
        description = html_to_text(str(row.get("job_description") or ""))
        if require_description and not description:
            continue
        absolute_url = str(row.get("job_url") or source_url)

        return JobDetails(
            source_url=source_url,
            normalized_source_url=normalize_snapshot_url(absolute_url),
            company_slug=company_slug,
            company_name=company_name,
            job_id=str(row.get("greenhouse_job_id") or ""),
            title=title,
            location=location,
            description=description,
            absolute_url=absolute_url,
        )

    return None


def snapshot_job_details(board: str | None, job_id: int, source_url: str) -> JobDetails | None:
    if not MATCHED_JOBS_PATH.exists():
        return None

    normalized_job_id = str(job_id)
    for row in load_jsonl(MATCHED_JOBS_PATH):
        row_job_id = clean_display_text(str(row.get("greenhouse_job_id") or ""))
        row_board = row.get("company_slug")
        if row_job_id != normalized_job_id:
            continue
        if board and row_board != board:
            continue

        company_slug = str(row_board or board or "")
        company_name = clean_display_text(str(row.get("company_name") or title_case_from_slug(company_slug)))
        title = clean_display_text(str(row.get("job_title") or "Untitled Role"))
        location = clean_display_text(str(row.get("job_location") or ""))
        description = html_to_text(str(row.get("job_description") or ""))
        absolute_url = str(row.get("job_url") or source_url)

        return JobDetails(
            source_url=source_url,
            normalized_source_url=normalize_snapshot_url(absolute_url),
            company_slug=company_slug,
            company_name=company_name,
            job_id=normalized_job_id,
            title=title,
            location=location,
            description=description,
            absolute_url=absolute_url,
        )

    return None


def fetch_workday_job_details(url: str) -> JobDetails | None:
    if not is_workday_url(url):
        return None

    snapshot_job = snapshot_job_details_by_url(url, require_description=False)
    html_text, final_url = fetch_url(url)
    job_posting = extract_job_posting_json_ld(html_text)
    if not job_posting:
        return None

    company_slug = snapshot_job.company_slug if snapshot_job is not None else infer_board_slug_from_host(final_url) or infer_board_slug_from_host(url) or ""
    company_name = snapshot_job.company_name if snapshot_job is not None else title_case_from_slug(company_slug)
    title = clean_display_text(str(job_posting.get("title") or "")) or (snapshot_job.title if snapshot_job is not None else "Untitled Role")
    location = clean_display_text(
        str((job_posting.get("jobLocation") or {}).get("address", {}).get("addressLocality") or "")
    )
    if not location:
        location = clean_display_text(str(job_posting.get("jobLocationType") or ""))
    if not location and snapshot_job is not None:
        location = snapshot_job.location
    description = clean_display_text(str(job_posting.get("description") or "")) or extract_open_graph_content(html_text, "og:description")
    absolute_url = extract_canonical_url(html_text) or final_url
    job_id = snapshot_job.job_id if snapshot_job is not None else workday_job_id_from_url(absolute_url) or workday_job_id_from_url(url)

    return JobDetails(
        source_url=url,
        normalized_source_url=normalize_snapshot_url(absolute_url),
        company_slug=company_slug,
        company_name=company_name,
        job_id=job_id,
        title=title,
        location=location,
        description=description,
        absolute_url=absolute_url,
    )


def fetch_job_details(url: str) -> JobDetails:
    snapshot_job = snapshot_job_details_by_url(url)
    if snapshot_job is not None:
        return snapshot_job

    workday_job = fetch_workday_job_details(url)
    if workday_job is not None:
        return workday_job

    board, job_id, normalized_source_url = resolve_greenhouse_job(url)
    try:
        payload = fetch_json(greenhouse_job_detail_url(board, job_id))
    except HTTPError as exc:
        if exc.code != 404:
            raise
        snapshot_job = snapshot_job_details(board, job_id, url)
        if snapshot_job is not None:
            return snapshot_job
        raise

    company_name = title_case_from_slug(board)
    title = clean_display_text(str(payload.get("title") or "Untitled Role"))
    location_obj = payload.get("location") or {}
    location = clean_display_text(str(location_obj.get("name") or ""))
    description = html_to_text(str(payload.get("content") or ""))
    absolute_url = str(payload.get("absolute_url") or normalized_source_url)

    return JobDetails(
        source_url=url,
        normalized_source_url=normalized_source_url,
        company_slug=board,
        company_name=company_name,
        job_id=str(job_id),
        title=title,
        location=location,
        description=description,
        absolute_url=absolute_url,
    )