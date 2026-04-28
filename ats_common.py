from __future__ import annotations

import asyncio
import html
import json
import re
import sys
import time
from html.parser import HTMLParser
from typing import Iterable


USER_AGENT = "greenhouse-job-crawler/0.1 (+personal job search automation)"

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


def log_step(message: str) -> None:
    print(f"[crawler] {message}", file=sys.stderr, flush=True)


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


def normalize_job_id(value: object) -> str:
    if isinstance(value, int):
        return str(value)
    return clean_display_text(str(value or ""))


def compile_title_pattern(title: str) -> re.Pattern[str]:
    normalized = normalize_match_text(title)
    escaped_tokens = [re.escape(token) for token in normalized.split()]
    pattern = r"\b" + r"\s+".join(escaped_tokens) + r"\b"
    return re.compile(pattern, re.IGNORECASE)


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


def html_to_text(html_text: str | None) -> str:
    if not html_text:
        return ""
    parser = HTMLTextExtractor()
    parser.feed(html_text)
    return parser.text


def is_target_location(location_name: str) -> bool:
    normalized_location = clean_display_text(location_name)
    if not normalized_location:
        return False
    if AUSTIN_LOCATION_PATTERN.search(normalized_location):
        return True
    return bool(REMOTE_LOCATION_PATTERN.search(normalized_location) and US_LOCATION_PATTERN.search(normalized_location))


def extract_canonical_url(html_text: str) -> str:
    match = re.search(r'<link\s+rel="canonical"\s+href="([^"]+)"', html_text, re.IGNORECASE)
    return clean_display_text(html.unescape(match.group(1))) if match is not None else ""


def extract_open_graph_content(html_text: str, property_name: str) -> str:
    pattern = rf'<meta\s+name="[^"]*"\s+property="{re.escape(property_name)}"\s+content="([^"]*)"'
    match = re.search(pattern, html_text, re.IGNORECASE)
    return clean_display_text(html.unescape(match.group(1))) if match is not None else ""


def unescape_json_strings(value: object) -> object:
    if isinstance(value, str):
        return html.unescape(value)
    if isinstance(value, list):
        return [unescape_json_strings(item) for item in value]
    if isinstance(value, dict):
        return {key: unescape_json_strings(item) for key, item in value.items()}
    return value


def extract_job_posting_json_ld(html_text: str) -> dict:
    for match in re.finditer(
        r'<script\s+type="application/ld\+json">\s*(.*?)\s*</script>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    ):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("@type") == "JobPosting":
            return unescape_json_strings(payload)
    return {}