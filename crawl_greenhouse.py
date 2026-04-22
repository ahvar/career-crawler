#!/usr/bin/env python3
"""
Greenhouse-only job crawler for a fixed list of target companies.

The crawler intentionally skips Gregslist and company-homepage discovery. It:
- generates likely Greenhouse board slugs for each target company
- probes the Greenhouse public jobs API until it finds a live board
- fetches job detail payloads for the board's open jobs
- filters jobs by target title families
- writes a fresh matched-jobs snapshot to crawler_cache/matched_jobs.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


DEFAULT_DELAY_SECONDS = 0.4
DEFAULT_CONCURRENCY = 4
DEFAULT_TIMEOUT_SECONDS = 20
USER_AGENT = "greenhouse-job-crawler/0.1 (+personal job search automation)"
VALID_JOB_TRACKING_STATUSES = ("pending_review", "applied", "revisit_later", "not_a_fit", "archived")

CACHE_DIR = Path("crawler_cache")
MATCHED_JOBS_PATH = CACHE_DIR / "matched_jobs.jsonl"
SEARCHED_COMPANIES_PATH = CACHE_DIR / "careers_scraped.jsonl"
NON_GREENHOUSE_COMPANIES_PATH = CACHE_DIR / "non_greenhouse_companies.txt"
JOB_TRACKING_PATH = CACHE_DIR / "job_tracking.jsonl"
COMPANY_REVISIT_PATH = CACHE_DIR / "company_revisit.jsonl"
ARCHIVE_DIR = CACHE_DIR / "archive"

GREENHOUSE_API_ROOT = "https://boards-api.greenhouse.io/v1/boards"
GREENHOUSE_BOARD_ROOT = "https://boards.greenhouse.io"

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

# Optional seed candidates for names that are likely to need a non-trivial slug.
COMPANY_SLUG_HINTS: dict[str, tuple[str, ...]] = {
    "Affirm": ("affirm",),
    "Striveworks": ("striveworks",),
    "Instacart": ("instacart",),
    "Elastic": ("elastic",),
    "Doximity": ("doximity",),
    "Reddit": ("reddit",),
    "Surfside": ("surfside",),
    "Glacis": ("glacis",),
    "Stealth": ("stealth",),
    "DeepSense": ("deepsense", "deep-sense"),
    "Kovo": ("kovo",),
    "Finch Care": ("finchcare", "finch-care"),
    "MindCloud": ("mindcloud", "mind-cloud"),
    "Spawn": ("spawn",),
    "Helm Health": ("helmhealth", "helm-health"),
}

ROLE_FAMILY_TITLES = {
    "software_engineering": (
        "Software Engineer",
        "Python Software Engineer",
        "Python Software Developer",
        "Senior Software Engineer",
        "Senior Developer",
        "Backend Developer",
        "Backend Software Engineer",
        "Programmer",
        "Python Developer",
        "Python Programmer",
        "Applications Developer",
        "Applications Engineer",
        "Developer",
        "Data Engineer",
        "Senior Data Engineer",
        "Bioinformatics Software Engineer",
        "Software Engineer in Bioinformatics",
        "Bioinformatics Scientist",
        "Bioinformatics Engineer",
        "Bioinformatician",
        "AI Engineer",
        "Product Engineer",
        "DevOps Engineer",
        "QA Engineer",
        "Quality Assurance Engineer",
        "Test Engineer",
    ),
    "solutions_engineering": (
        "Solutions Engineer",
        "Technical Account Manager",
        "Customer Success Engineer",
        "Customer Solutions Engineer",
        "Solutions Architect",
        "Implementation Specialist",
        "Integration Specialist",
        "Technical Trainer",
        "Training Specialist",
        "Customer Onboarding Specialist",
        "Technical Coordinator",
    ),
    "technical_support_engineering": (
        "Technical Support Engineer",
        "Tier 2 Support",
        "Tier 3 Support",
        "Scientific Support Specialist",
        "Technical Support Specialist",
        "Product Support Specialist",
        "Application Specialist",
        "IT Help Desk Representative",
    ),
    "technical_writing": (
        "Technical Writer",
    ),
}

EXCLUDED_ROLE_HINTS = (
    "account executive",
    "sales representative",
    "sales development representative",
    "business development representative",
    "revenue operations",
    "field sales",
)

AUSTIN_LOCATION_PATTERN = re.compile(r"\baustin(?:\s*,)?\s*(?:tx|texas)\b", re.IGNORECASE)
REMOTE_LOCATION_PATTERN = re.compile(r"\b(remote|distributed|work from home|home based)\b", re.IGNORECASE)
US_LOCATION_PATTERN = re.compile(r"\b(?:united states|u\.?\s*s\.?\s*a?\.?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class TargetCompany:
    name: str
    slug_candidates: tuple[str, ...] = ()


@dataclass
class MatchedJob:
    company_name: str
    company_slug: str
    careers_url: str
    greenhouse_job_id: int
    job_title: str
    job_url: str
    job_location: str
    matched_keywords: list[str]
    matched_role_families: list[str]
    found_date: str
    job_description: str


@dataclass
class CompanyAssessment:
    name: str
    attempted_slugs: list[str]
    resolved_slug: str | None
    board_url: str | None
    status: str
    jobs_seen: int = 0
    matched_jobs: list[MatchedJob] = field(default_factory=list)


@dataclass
class CrawlRun:
    assessments: list[CompanyAssessment]
    matched_jobs: list[MatchedJob]


@dataclass(frozen=True)
class JobMatchResult:
    matched_job: MatchedJob | None
    title_matched: bool = False
    location_matched: bool = False


class CrawlError(RuntimeError):
    """Raised when crawling cannot proceed safely."""


def log_step(message: str) -> None:
    print(f"[crawler] {message}", file=sys.stderr, flush=True)


def ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)


def ensure_tracking_files() -> None:
    ensure_cache_dir()
    for path in (JOB_TRACKING_PATH, COMPANY_REVISIT_PATH):
        if not path.exists():
            path.write_text("", encoding="utf-8")


def atomic_write(path: Path, text: str) -> None:
    ensure_cache_dir()
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)


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


def count_jsonl_rows(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def summarize_output_stats() -> str:
    ensure_cache_dir()
    ensure_tracking_files()
    archived_match_files = sorted(ARCHIVE_DIR.glob("matched_jobs*.jsonl"))
    lines = [
        f"Output file: {MATCHED_JOBS_PATH}",
        f"Current matched jobs: {count_jsonl_rows(MATCHED_JOBS_PATH)}",
        f"Searched companies cache: {len(load_company_search_cache())}",
        f"Known non-Greenhouse companies: {count_text_rows(NON_GREENHOUSE_COMPANIES_PATH)}",
        f"Tracked jobs: {count_jsonl_rows(JOB_TRACKING_PATH)}",
        f"Tracked company revisits: {count_jsonl_rows(COMPANY_REVISIT_PATH)}",
        f"Archived matched-job files: {len(archived_match_files)}",
    ]
    return "\n".join(lines)


def count_text_rows(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def normalize_match_text(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[_/|]+", " ", lowered)
    lowered = re.sub(r"[^a-z0-9+&.-]+", " ", lowered)
    return " ".join(lowered.split())


def clean_display_text(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


def company_cache_key(name: str) -> str:
    return normalize_match_text(name)


TARGET_TITLES = tuple(
    dict.fromkeys(title for titles in ROLE_FAMILY_TITLES.values() for title in titles)
)


def compile_title_pattern(title: str) -> re.Pattern[str]:
    normalized = normalize_match_text(title)
    escaped_tokens = [re.escape(token) for token in normalized.split()]
    pattern = r"\b" + r"\s+".join(escaped_tokens) + r"\b"
    return re.compile(pattern, re.IGNORECASE)


TITLE_PATTERNS = {title: compile_title_pattern(title) for title in TARGET_TITLES}
ROLE_FAMILY_TITLE_PATTERNS = {
    family: {title: compile_title_pattern(title) for title in titles}
    for family, titles in ROLE_FAMILY_TITLES.items()
}


def infer_title_matches(text: str) -> tuple[list[str], list[str]]:
    normalized = normalize_match_text(text)
    if not normalized:
        return [], []
    if any(excluded in normalized for excluded in EXCLUDED_ROLE_HINTS):
        return [], []

    matched_keywords: list[str] = []
    matched_role_families: list[str] = []
    for family, patterns in ROLE_FAMILY_TITLE_PATTERNS.items():
        family_matches = [title.lower() for title, pattern in patterns.items() if pattern.search(normalized)]
        if family_matches:
            matched_role_families.append(family)
            matched_keywords.extend(family_matches)

    return dedupe_preserve_order(matched_keywords), dedupe_preserve_order(matched_role_families)


class AsyncRateLimiter:
    """Allow only one outbound request per configured interval."""

    def __init__(self, min_delay_seconds: float) -> None:
        self.min_delay_seconds = min_delay_seconds
        self._lock = asyncio.Lock()
        self._last_request_at = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            remaining = self.min_delay_seconds - (now - self._last_request_at)
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_request_at = time.monotonic()


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


def html_to_text(html: str | None) -> str:
    if not html:
        return ""
    parser = HTMLTextExtractor()
    parser.feed(html)
    return parser.text


def build_slug_candidates(company_name: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", company_name.lower())
    if not tokens:
        return []

    hinted = list(COMPANY_SLUG_HINTS.get(company_name, ()))
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


def load_jsonl_records(path: Path) -> list[dict]:
    if not path.exists():
        return []

    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def save_jsonl_records(path: Path, records: Iterable[dict]) -> int:
    serialized_lines = [json.dumps(record, sort_keys=True) for record in records]
    text = "\n".join(serialized_lines)
    if text:
        text += "\n"
    atomic_write(path, text)
    return len(serialized_lines)


def matched_job_key(company_slug: str, greenhouse_job_id: int) -> tuple[str, int]:
    return company_slug, greenhouse_job_id


def load_matched_jobs_snapshot() -> list[MatchedJob]:
    jobs: list[MatchedJob] = []
    for record in load_jsonl_records(MATCHED_JOBS_PATH):
        company_slug = clean_display_text(str(record.get("company_slug") or ""))
        job_id = record.get("greenhouse_job_id")
        if not company_slug or not isinstance(job_id, int):
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


def normalize_job_tracking_record(record: dict) -> dict | None:
    company_slug = clean_display_text(str(record.get("company_slug") or ""))
    greenhouse_job_id = record.get("greenhouse_job_id")
    if not company_slug or not isinstance(greenhouse_job_id, int):
        return None
    return {
        "company_slug": company_slug,
        "greenhouse_job_id": greenhouse_job_id,
        "job_url": clean_display_text(str(record.get("job_url") or "")),
        "status": clean_display_text(str(record.get("status") or "pending_review")) or "pending_review",
        "review_date": clean_display_text(str(record.get("review_date") or "")),
        "application_date": clean_display_text(str(record.get("application_date") or "")),
        "next_action_date": clean_display_text(str(record.get("next_action_date") or "")),
        "notes": clean_display_text(str(record.get("notes") or "")),
        "match_rationale": clean_display_text(str(record.get("match_rationale") or "")),
    }


def load_job_tracking_records() -> dict[tuple[str, int], dict]:
    ensure_tracking_files()
    records: dict[tuple[str, int], dict] = {}
    for record in load_jsonl_records(JOB_TRACKING_PATH):
        normalized = normalize_job_tracking_record(record)
        if normalized is None:
            continue
        records[matched_job_key(normalized["company_slug"], normalized["greenhouse_job_id"])] = normalized
    return records


def save_job_tracking_records(records: dict[tuple[str, int], dict]) -> int:
    serialized = [records[key] for key in sorted(records, key=lambda item: (item[0], item[1]))]
    return save_jsonl_records(JOB_TRACKING_PATH, serialized)


def normalize_company_revisit_record(record: dict) -> dict | None:
    company_slug = clean_display_text(str(record.get("company_slug") or ""))
    company_name = clean_display_text(str(record.get("company_name") or ""))
    if not company_slug or not company_name:
        return None
    return {
        "company_slug": company_slug,
        "company_name": company_name,
        "board_type": clean_display_text(str(record.get("board_type") or "unknown")) or "unknown",
        "last_checked": clean_display_text(str(record.get("last_checked") or "")),
        "next_revisit": clean_display_text(str(record.get("next_revisit") or "")),
        "reason": clean_display_text(str(record.get("reason") or "")),
        "notes": clean_display_text(str(record.get("notes") or "")),
    }


def load_company_revisit_records() -> dict[str, dict]:
    ensure_tracking_files()
    records: dict[str, dict] = {}
    for record in load_jsonl_records(COMPANY_REVISIT_PATH):
        normalized = normalize_company_revisit_record(record)
        if normalized is None:
            continue
        records[normalized["company_slug"]] = normalized
    return records


def parse_iso_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def get_matched_job_snapshot_record(company_slug: str, greenhouse_job_id: int) -> MatchedJob | None:
    for job in load_matched_jobs_snapshot():
        if matched_job_key(job.company_slug, job.greenhouse_job_id) == (company_slug, greenhouse_job_id):
            return job
    return None


def upsert_job_tracking_record(
    *,
    company_slug: str,
    greenhouse_job_id: int,
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
    key = matched_job_key(company_slug, greenhouse_job_id)
    existing = records.get(key)
    snapshot_job = get_matched_job_snapshot_record(company_slug, greenhouse_job_id)
    if existing is None and snapshot_job is None:
        raise CrawlError(
            f"Job {greenhouse_job_id} for company slug '{company_slug}' was not found in the current snapshot or tracking overlay."
        )

    today_iso = date.today().isoformat()
    base_record = existing or {
        "company_slug": company_slug,
        "greenhouse_job_id": greenhouse_job_id,
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


def format_tracking_report() -> str:
    ensure_tracking_files()
    today = date.today()
    matched_jobs = load_matched_jobs_snapshot()
    tracked_jobs = load_job_tracking_records()
    company_revisits = load_company_revisit_records()

    matched_jobs_by_key = {
        matched_job_key(job.company_slug, job.greenhouse_job_id): job
        for job in matched_jobs
    }
    jobs_with_tracking: list[tuple[MatchedJob, dict]] = []
    missing_jobs: list[dict] = []
    for key, record in tracked_jobs.items():
        matched_job = matched_jobs_by_key.get(key)
        if matched_job is None:
            missing_jobs.append(record)
        else:
            jobs_with_tracking.append((matched_job, record))

    status_counts: dict[str, int] = {}
    for record in tracked_jobs.values():
        status = record["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    due_companies = [
        record for record in company_revisits.values()
        if (due_date := parse_iso_date(record["next_revisit"])) is not None and due_date <= today
    ]
    upcoming_companies = [
        record for record in company_revisits.values()
        if (due_date := parse_iso_date(record["next_revisit"])) is not None and due_date > today
    ]
    due_companies.sort(key=lambda record: record["next_revisit"])
    upcoming_companies.sort(key=lambda record: record["next_revisit"])

    lines = [
        "Tracking Report",
        f"Today: {today.isoformat()}",
        f"Matched jobs snapshot: {len(matched_jobs)}",
        f"Tracked jobs: {len(tracked_jobs)}",
        f"Tracked companies with revisit dates: {len(company_revisits)}",
    ]

    if status_counts:
        lines.append("Tracked job statuses:")
        for status in sorted(status_counts):
            lines.append(f"- {status}: {status_counts[status]}")
    else:
        lines.append("Tracked job statuses: none yet")

    lines.append("")
    lines.append("Tracked Jobs In Current Snapshot")
    if jobs_with_tracking:
        for job, record in sorted(jobs_with_tracking, key=lambda item: (item[1]["status"], item[0].company_name, item[0].job_title)):
            details = [
                f"{record['status']}",
                f"{job.company_name} | {job.job_title}",
            ]
            if record["next_action_date"]:
                details.append(f"next action {record['next_action_date']}")
            if record["notes"]:
                details.append(record["notes"])
            lines.append(f"- {'; '.join(details)}")
            lines.append(f"  {job.job_url}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Tracked Jobs Missing From Current Snapshot")
    if missing_jobs:
        for record in sorted(missing_jobs, key=lambda item: (item["status"], item["company_slug"], item["greenhouse_job_id"])):
            details = [
                record["status"],
                f"{record['company_slug']} | {record['greenhouse_job_id']}",
            ]
            if record["next_action_date"]:
                details.append(f"next action {record['next_action_date']}")
            if record["notes"]:
                details.append(record["notes"])
            lines.append(f"- {'; '.join(details)}")
            if record["job_url"]:
                lines.append(f"  {record['job_url']}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Companies Due For Revisit")
    if due_companies:
        for record in due_companies:
            details = [
                record["company_name"],
                f"board={record['board_type']}",
                f"next revisit {record['next_revisit']}",
            ]
            if record["reason"]:
                details.append(record["reason"])
            lines.append(f"- {'; '.join(details)}")
    else:
        lines.append("- none due today")

    lines.append("")
    lines.append("Upcoming Company Revisits")
    if upcoming_companies:
        for record in upcoming_companies:
            details = [
                record["company_name"],
                f"board={record['board_type']}",
                f"next revisit {record['next_revisit']}",
            ]
            if record["reason"]:
                details.append(record["reason"])
            lines.append(f"- {'; '.join(details)}")
    else:
        lines.append("- none scheduled")

    return "\n".join(lines)


def load_company_search_cache() -> dict[str, dict]:
    records_by_company: dict[str, dict] = {}
    for record in load_jsonl_records(SEARCHED_COMPANIES_PATH):
        source = clean_display_text(str(record.get("source") or ""))
        resolved_slug = clean_display_text(str(record.get("resolved_slug") or ""))
        if source != "greenhouse" and not resolved_slug:
            continue
        company_name = clean_display_text(str(record.get("company_name") or ""))
        if not company_name:
            continue
        records_by_company[company_cache_key(company_name)] = record
    return records_by_company


def save_company_search_cache(records_by_company: dict[str, dict]) -> int:
    serialized_lines = [
        json.dumps(records_by_company[key], sort_keys=True)
        for key in sorted(records_by_company, key=lambda item: records_by_company[item].get("company_name", ""))
    ]
    text = "\n".join(serialized_lines)
    if text:
        text += "\n"
    atomic_write(SEARCHED_COMPANIES_PATH, text)
    return len(serialized_lines)


def load_non_greenhouse_companies() -> dict[str, str]:
    if not NON_GREENHOUSE_COMPANIES_PATH.exists():
        return {}

    companies_by_key: dict[str, str] = {}
    for line in NON_GREENHOUSE_COMPANIES_PATH.read_text(encoding="utf-8").splitlines():
        company_name = clean_display_text(line)
        if not company_name:
            continue
        companies_by_key[company_cache_key(company_name)] = company_name
    return companies_by_key


def save_non_greenhouse_companies(companies_by_key: dict[str, str]) -> int:
    company_names = [companies_by_key[key] for key in sorted(companies_by_key, key=lambda item: companies_by_key[item].lower())]
    text = "\n".join(company_names)
    if text:
        text += "\n"
    atomic_write(NON_GREENHOUSE_COMPANIES_PATH, text)
    return len(company_names)


def build_cached_assessment(company_name: str, record: dict, status: str) -> CompanyAssessment:
    resolved_slug = clean_display_text(str(record.get("resolved_slug") or ""))
    board_url = clean_display_text(str(record.get("board_url") or ""))
    jobs_seen = record.get("jobs_seen")
    matched_job_count = record.get("matched_job_count")
    matched_jobs = [None] * matched_job_count if isinstance(matched_job_count, int) and matched_job_count > 0 else []
    return CompanyAssessment(
        name=company_name,
        attempted_slugs=[],
        resolved_slug=resolved_slug or None,
        board_url=board_url or None,
        status=status,
        jobs_seen=jobs_seen if isinstance(jobs_seen, int) else 0,
        matched_jobs=matched_jobs,
    )


def is_target_location(location_name: str) -> bool:
    normalized_location = clean_display_text(location_name)
    if not normalized_location:
        return False
    if AUSTIN_LOCATION_PATTERN.search(normalized_location):
        return True
    return bool(
        REMOTE_LOCATION_PATTERN.search(normalized_location)
        and US_LOCATION_PATTERN.search(normalized_location)
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
        "source": "greenhouse",
    }


def greenhouse_jobs_url(slug: str) -> str:
    return f"{GREENHOUSE_API_ROOT}/{quote(slug, safe='')}/jobs"


def greenhouse_job_detail_url(slug: str, job_id: int) -> str:
    return f"{GREENHOUSE_API_ROOT}/{quote(slug, safe='')}/jobs/{job_id}"


def greenhouse_board_url(slug: str) -> str:
    return f"{GREENHOUSE_BOARD_ROOT}/{quote(slug, safe='')}"


class GreenhouseCrawler:
    def __init__(self, *, delay_seconds: float, concurrency: int, timeout_seconds: int) -> None:
        self.rate_limiter = AsyncRateLimiter(delay_seconds)
        self.semaphore = asyncio.Semaphore(concurrency)
        self.timeout_seconds = timeout_seconds
        self.today = date.today()

    async def crawl(self, companies: Iterable[TargetCompany]) -> CrawlRun:
        company_list = list(companies)
        log_step(f"Starting Greenhouse crawl for {len(company_list)} target companies")
        tasks = [self._crawl_company(company) for company in company_list]
        assessments = await asyncio.gather(*tasks)
        matched_jobs = [job for assessment in assessments for job in assessment.matched_jobs]
        written = save_matched_jobs(matched_jobs)
        log_step(f"Wrote {written} matched jobs to {MATCHED_JOBS_PATH}")
        return CrawlRun(assessments=assessments, matched_jobs=matched_jobs)

    async def _crawl_company(self, company: TargetCompany) -> CompanyAssessment:
        attempted_slugs = list(company.slug_candidates) or build_slug_candidates(company.name)
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
                return CompanyAssessment(
                    name=company.name,
                    attempted_slugs=attempted_slugs,
                    resolved_slug=slug,
                    board_url=greenhouse_board_url(slug),
                    status=f"HTTP {exc.code}",
                )
            except (URLError, TimeoutError) as exc:
                return CompanyAssessment(
                    name=company.name,
                    attempted_slugs=attempted_slugs,
                    resolved_slug=slug,
                    board_url=greenhouse_board_url(slug),
                    status=f"Network error: {exc}",
                )

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
            if matched_jobs:
                status = "Matched jobs found"
            elif title_matches and not location_matches:
                status = "No jobs in Austin/US-remote"
            else:
                status = "No matching job titles"
            return CompanyAssessment(
                name=company.name,
                attempted_slugs=attempted_slugs,
                resolved_slug=slug,
                board_url=greenhouse_board_url(slug),
                status=status,
                jobs_seen=len(job_summaries),
                matched_jobs=matched_jobs,
            )

        final_status = "No open jobs" if saw_empty_board else "Greenhouse board not found"
        return CompanyAssessment(
            name=company.name,
            attempted_slugs=attempted_slugs,
            resolved_slug=None,
            board_url=None,
            status=final_status,
        )

    async def _fetch_job_details(
        self,
        *,
        company_name: str,
        slug: str,
        jobs: list[dict],
    ) -> list[JobMatchResult]:
        tasks = [
            self._fetch_and_match_job_detail(company_name=company_name, slug=slug, job_summary=job_summary)
            for job_summary in jobs
        ]
        return await asyncio.gather(*tasks)

    async def _fetch_and_match_job_detail(
        self,
        *,
        company_name: str,
        slug: str,
        job_summary: dict,
    ) -> JobMatchResult:
        job_id = job_summary.get("id")
        if not isinstance(job_id, int):
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
        job_description = html_to_text(str(detail_payload.get("content") or ""))
        job_url = str(detail_payload.get("absolute_url") or job_summary.get("absolute_url") or greenhouse_board_url(slug))
        board_url = greenhouse_board_url(slug)

        return JobMatchResult(
            matched_job=MatchedJob(
                company_name=company_name,
                company_slug=slug,
                careers_url=board_url,
                greenhouse_job_id=job_id,
                job_title=title or "Unknown Role",
                job_url=job_url,
                job_location=location_name,
                matched_keywords=matched_keywords,
                matched_role_families=matched_role_families,
                found_date=self.today.isoformat(),
                job_description=job_description,
            ),
            title_matched=True,
            location_matched=True,
        )

    async def _fetch_json(self, url: str) -> dict:
        async with self.semaphore:
            await self.rate_limiter.wait()
            return await asyncio.to_thread(self._fetch_json_blocking, url)

    def _fetch_json_blocking(self, url: str) -> dict:
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise HTTPError(url, status, f"Unexpected status {status}", hdrs=None, fp=None)
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset, errors="replace"))


def format_results(rows: Iterable[CompanyAssessment]) -> str:
    results = list(rows)
    if not results:
        return "No company results were collected."

    company_width = max(len("Company"), *(len(result.name) for result in results))
    slug_cells = [result.resolved_slug or "-" for result in results]
    slug_width = max(len("Slug"), *(len(cell) for cell in slug_cells))
    jobs_width = max(len("Jobs"), *(len(str(result.jobs_seen)) for result in results))
    matches_width = max(len("Matches"), *(len(str(len(result.matched_jobs))) for result in results))
    status_width = max(len("Status"), *(len(result.status) for result in results))

    lines = [
        f"{'Company'.ljust(company_width)}  "
        f"{'Slug'.ljust(slug_width)}  "
        f"{'Jobs'.rjust(jobs_width)}  "
        f"{'Matches'.rjust(matches_width)}  "
        f"{'Status'.ljust(status_width)}",
        f"{'-' * company_width}  {'-' * slug_width}  {'-' * jobs_width}  {'-' * matches_width}  {'-' * status_width}",
    ]
    for result, slug_cell in zip(results, slug_cells):
        lines.append(
            f"{result.name.ljust(company_width)}  "
            f"{slug_cell.ljust(slug_width)}  "
            f"{str(result.jobs_seen).rjust(jobs_width)}  "
            f"{str(len(result.matched_jobs)).rjust(matches_width)}  "
            f"{result.status.ljust(status_width)}"
        )
    return "\n".join(lines)


def format_matched_jobs(jobs: Iterable[MatchedJob]) -> str:
    job_list = list(jobs)
    if not job_list:
        return ""

    company_width = max(len("Company"), *(len(job.company_name) for job in job_list))
    title_width = max(len("Job Title"), *(len(job.job_title) for job in job_list))
    location_width = max(len("Location"), *(len(job.job_location or "-") for job in job_list))
    url_width = max(len("Job URL"), *(len(job.job_url) for job in job_list))

    lines = [
        "",
        "Matched Jobs",
        f"{'Company'.ljust(company_width)}  {'Job Title'.ljust(title_width)}  {'Location'.ljust(location_width)}  {'Job URL'.ljust(url_width)}",
        f"{'-' * company_width}  {'-' * title_width}  {'-' * location_width}  {'-' * url_width}",
    ]
    for job in job_list:
        lines.append(
            f"{job.company_name.ljust(company_width)}  "
            f"{job.job_title.ljust(title_width)}  "
            f"{(job.job_location or '-').ljust(location_width)}  "
            f"{job.job_url.ljust(url_width)}"
        )
    return "\n".join(lines)


def format_matched_job_urls(jobs: Iterable[MatchedJob]) -> str:
    job_list = list(jobs)
    if not job_list:
        return ""

    lines = ["", "Matched Job URLs"]
    lines.extend(job.job_url for job in job_list)
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Greenhouse-only job crawler for target companies.")
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
        "--set-job-status",
        choices=VALID_JOB_TRACKING_STATUSES,
        help="Upsert a job-level tracking record in crawler_cache/job_tracking.jsonl.",
    )
    parser.add_argument(
        "--company-slug",
        help="Company slug for a job tracking update, for example 'affirm' or 'instacart'.",
    )
    parser.add_argument(
        "--job-id",
        type=int,
        help="Greenhouse job id for a job tracking update.",
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
    if args.set_job_status and (not args.company_slug or args.job_id is None):
        parser.error("--set-job-status requires both --company-slug and --job-id.")
    if not args.set_job_status and any(
        value is not None
        for value in (args.company_slug, args.job_id, args.review_date, args.application_date, args.next_action_date, args.notes, args.match_rationale)
    ):
        parser.error("Job tracking update flags require --set-job-status.")
    for value, flag_name in (
        (args.review_date, "--review-date"),
        (args.application_date, "--application-date"),
        (args.next_action_date, "--next-action-date"),
    ):
        if value not in (None, "") and parse_iso_date(value) is None:
            parser.error(f"{flag_name} must use YYYY-MM-DD format.")
    return args


async def run(
    *,
    company_names: list[str],
    limit: int,
    delay: float,
    concurrency: int,
    timeout: int,
    show_cache_stats: bool,
    show_company_list: bool,
    show_tracking_report: bool,
    set_job_status: str | None,
    company_slug: str | None,
    job_id: int | None,
    review_date: str | None,
    application_date: str | None,
    next_action_date: str | None,
    notes: str | None,
    match_rationale: str | None,
) -> int:
    ensure_cache_dir()
    ensure_tracking_files()

    if show_company_list:
        for company_name in DEFAULT_TARGET_COMPANIES:
            print(company_name)
        return 0

    if show_cache_stats:
        print(summarize_output_stats())
        return 0

    if show_tracking_report:
        print(format_tracking_report())
        return 0

    if set_job_status is not None:
        updated = upsert_job_tracking_record(
            company_slug=clean_display_text(company_slug or ""),
            greenhouse_job_id=job_id or 0,
            status=set_job_status,
            review_date=review_date,
            application_date=application_date,
            next_action_date=next_action_date,
            notes=notes,
            match_rationale=match_rationale,
        )
        print(json.dumps(updated, indent=2, sort_keys=True))
        return 0

    search_cache = load_company_search_cache()
    non_greenhouse_cache = load_non_greenhouse_companies()

    skipped_assessments: list[CompanyAssessment] = []
    if company_names:
        selected_company_names = company_names[:limit]
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
            if len(selected_company_names) >= limit:
                break

    targets = build_target_companies(selected_company_names)
    if not targets and not skipped_assessments:
        raise CrawlError("No target companies were provided.")
    if not targets:
        print(format_results(skipped_assessments))
        return 0

    crawler = GreenhouseCrawler(
        delay_seconds=delay,
        concurrency=concurrency,
        timeout_seconds=timeout,
    )
    crawl_run = await crawler.crawl(targets)
    today_iso = crawler.today.isoformat()

    for assessment in crawl_run.assessments:
        search_cache[company_cache_key(assessment.name)] = build_search_record(assessment, today_iso=today_iso)
        if assessment.status == "Greenhouse board not found":
            non_greenhouse_cache[company_cache_key(assessment.name)] = assessment.name
        else:
            non_greenhouse_cache.pop(company_cache_key(assessment.name), None)

    written_search_records = save_company_search_cache(search_cache)
    written_non_greenhouse = save_non_greenhouse_companies(non_greenhouse_cache)
    log_step(f"Updated {written_search_records} search-cache records in {SEARCHED_COMPANIES_PATH}")
    log_step(f"Recorded {written_non_greenhouse} non-Greenhouse companies in {NON_GREENHOUSE_COMPANIES_PATH}")

    assessments = skipped_assessments + crawl_run.assessments
    output = format_results(assessments)
    matched_jobs_section = format_matched_jobs(crawl_run.matched_jobs)
    matched_urls_section = format_matched_job_urls(crawl_run.matched_jobs)
    print(output + matched_jobs_section + matched_urls_section)
    return 0


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(
            run(
                company_names=args.company,
                limit=args.limit,
                delay=args.delay,
                concurrency=args.concurrency,
                timeout=args.timeout,
                show_cache_stats=args.show_cache_stats,
                show_company_list=args.show_company_list,
                show_tracking_report=args.show_tracking_report,
                set_job_status=args.set_job_status,
                company_slug=args.company_slug,
                job_id=args.job_id,
                review_date=args.review_date,
                application_date=args.application_date,
                next_action_date=args.next_action_date,
                notes=args.notes,
                match_rationale=args.match_rationale,
            )
        )
    except CrawlError as exc:
        print(f"Crawl blocked: {exc}", file=sys.stderr)
        return 2
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
