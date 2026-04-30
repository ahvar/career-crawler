#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Config
from application_materials_templates import (
    CoverLetterContent,
    ResumeContent,
    TemplateConfig,
    document_to_text,
    extract_template_resume_content,
    infer_generation_role_family,
    render_cover_letter_docx,
    render_resume_docx,
    template_config_for_role_family,
)


APPLICATION_MATERIALS_DIR = ROOT / "application_materials"
GENERATED_DIR = ROOT / "application_materials" / "generated"
GENERATED_JOB_DESCRIPTIONS_DIR = GENERATED_DIR / "job_descriptions"
DERIVED_PROFILE_DIR = ROOT / "derived_profile"
CRAWLER_CACHE_DIR = ROOT / "crawler_cache"
MATCHED_JOBS_PATH = CRAWLER_CACHE_DIR / "matched_jobs.jsonl"

USER_AGENT = Config.USER_AGENT or "application-material-generator/0.1"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_TEST_URLS = (
    "https://job-boards.greenhouse.io/affirm/jobs/7594302003",
    "https://www.instacart.careers/job?id=7831409",
)


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
    job_id: int
    title: str
    location: str
    description: str
    absolute_url: str


@dataclass(frozen=True)
class CandidateContext:
    profile_summary: str
    canonical_profile: dict[str, Any]
    evidence_bank: list[dict[str, Any]]
    style_samples: list[dict[str, Any]]


def clean_display_text(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


def normalize_match_text(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[_/|]+", " ", lowered)
    lowered = re.sub(r"[^a-z0-9+&.-]+", " ", lowered)
    return " ".join(lowered.split())


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


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


def fetch_job_details(url: str) -> JobDetails:
    snapshot_job = snapshot_job_details_by_url(url)
    if snapshot_job is not None:
        return snapshot_job

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
        job_id=job_id,
        title=title,
        location=location,
        description=description,
        absolute_url=absolute_url,
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def normalize_snapshot_url(url: str) -> str:
    return url.strip().rstrip("/")


def snapshot_job_details_by_url(source_url: str) -> JobDetails | None:
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
        absolute_url = str(row.get("job_url") or source_url)

        return JobDetails(
            source_url=source_url,
            normalized_source_url=absolute_url,
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

    for row in load_jsonl(MATCHED_JOBS_PATH):
        row_job_id = row.get("greenhouse_job_id")
        row_board = row.get("company_slug")
        if row_job_id != job_id:
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
            normalized_source_url=absolute_url,
            company_slug=company_slug,
            company_name=company_name,
            job_id=job_id,
            title=title,
            location=location,
            description=description,
            absolute_url=absolute_url,
        )

    return None


def load_candidate_context() -> CandidateContext:
    return CandidateContext(
        profile_summary=(DERIVED_PROFILE_DIR / "profile_summary.md").read_text(encoding="utf-8"),
        canonical_profile=load_json(DERIVED_PROFILE_DIR / "canonical_profile.json"),
        evidence_bank=load_jsonl(DERIVED_PROFILE_DIR / "evidence_bank.jsonl"),
        style_samples=load_jsonl(DERIVED_PROFILE_DIR / "style_samples.jsonl"),
    )


STOP_WORDS = {
    "the", "and", "with", "that", "this", "from", "your", "have", "will", "for", "are", "you", "our", "role",
    "job", "team", "work", "experience", "about", "into", "their", "they", "them", "through", "using", "used",
    "build", "building", "software", "engineer", "engineering", "systems", "backend", "remote", "united", "states",
}

DEFAULT_SKILL_LABELS = (
    "Languages & Frameworks:",
    "Databases & Data:",
    "Cloud & DevOps:",
    "Workflow & Orchestration:",
)

DEFAULT_WRITER_COMPETENCY_LABELS = (
    "Developer Documentation",
    "Docs-as-Code & Publishing",
    "Programming & APIs",
    "Cloud & Infrastructure",
    "AI-Assisted Workflows",
)

SKILL_CATEGORY_CANDIDATES = (
    ("Backend & APIs:", ("backend", "api", "apis", "service", "services", "microservice", "microservices", "integration", "integrations", "distributed", "python", "flask")),
    ("Data & Persistence:", ("data", "database", "databases", "sql", "postgres", "mysql", "storage", "query", "search", "elasticsearch", "redis")),
    ("Cloud & Infrastructure:", ("cloud", "aws", "docker", "kubernetes", "container", "containers", "ecs", "infrastructure", "deployment")),
    ("Delivery & Quality:", ("ci/cd", "cicd", "testing", "release", "reliability", "monitoring", "automation", "devops", "codepipeline", "codebuild")),
    ("Workflow & Automation:", ("workflow", "orchestration", "pipeline", "pipelines", "event", "event-driven", "scheduler", "batch", "nextflow", "automation")),
)

WRITER_COMPETENCY_SLOT_CANDIDATES = (
    (
        "Developer Documentation",
        (
            ("API Documentation", ("api", "apis", "reference", "endpoint", "endpoints", "sdk")),
            ("Developer Guides & Tutorials", ("guide", "guides", "tutorial", "tutorials", "walkthrough", "walkthroughs", "onboarding")),
            ("Release Notes & Product Documentation", ("release", "releases", "release notes", "product", "features", "changelog")),
            ("Information Architecture & Standards", ("information architecture", "taxonomy", "style guide", "style guides", "standards", "consistency")),
        ),
    ),
    (
        "Docs-as-Code & Publishing",
        (
            ("Docs-as-Code & Publishing", ("markdown", "docs-as-code", "docs as code", "git", "github", "publishing", "static site", "sphinx")),
            ("Documentation Tooling", ("confluence", "jira", "html", "tooling", "workflow", "cms")),
        ),
    ),
    (
        "Programming & APIs",
        (
            ("Programming & APIs", ("python", "rest", "flask", "json", "cli", "code", "coding", "api", "apis")),
            ("Developer Tooling", ("developer", "developers", "tooling", "automation")),
        ),
    ),
    (
        "Cloud & Infrastructure",
        (
            ("Cloud & Infrastructure", ("aws", "cloud", "docker", "kubernetes", "infrastructure", "devops", "ci/cd", "cicd")),
            ("Platform & Deployment", ("deployment", "deployments", "platform", "platforms", "container", "containers")),
        ),
    ),
    (
        "AI-Assisted Workflows",
        (
            ("AI-Assisted Documentation Workflows", ("ai", "llm", "rag", "agent", "agents", "automation")),
            ("AI-Assisted Workflows", ("copilot", "chatgpt", "codex")),
        ),
    ),
)

ROLE_FAMILY_EVIDENCE_TAGS = {
    "software_engineering": ("software_engineering",),
    "solutions_engineering": ("solutions_engineering", "developer_relations_or_support", "technical_support"),
    "technical_support_engineering": ("technical_support", "developer_relations_or_support"),
    "technical_writing": ("technical_writing", "developer_relations_or_support"),
}

SOFTWARE_ENGINEERING_SKILL_SUPPORT_SOURCE_FILE = "resumes_cov_letters/archive/vargas_software_engineer_resume.docx"

CUSTOMER_FACING_SKILL_SOURCE_ORDER = {
    "solutions_engineering": (
        "skills/paragraph_12",
        "skills/paragraph_11",
        "skills/paragraph_16",
        "skills/paragraph_14",
        "skills/paragraph_13",
        "skills/paragraph_15",
    ),
    "technical_support_engineering": (
        "skills/paragraph_11",
        "skills/paragraph_12",
        "skills/paragraph_13",
        "skills/paragraph_14",
        "skills/paragraph_15",
        "skills/paragraph_16",
    ),
    "technical_writing": (
        "skills/paragraph_16",
        "skills/paragraph_11",
        "skills/paragraph_12",
        "skills/paragraph_14",
        "skills/paragraph_13",
        "skills/paragraph_15",
    ),
}


def tokenize(text: str) -> set[str]:
    return {token for token in normalize_match_text(text).split() if len(token) >= 3 and token not in STOP_WORDS}


def score_evidence(job_tokens: set[str], evidence: dict[str, Any], role_family: str) -> int:
    evidence_tokens = tokenize(str(evidence.get("text") or ""))
    overlap = len(job_tokens & evidence_tokens)
    score = overlap * 3
    if evidence.get("strength") == "strong":
        score += 4
    if evidence.get("is_quantified"):
        score += 1
    score += len(evidence.get("skill_tags") or [])
    score += len(evidence.get("role_tags") or [])

    desired_tags = set(ROLE_FAMILY_EVIDENCE_TAGS.get(role_family, ()))
    actual_tags = set(evidence.get("role_tags") or [])
    if desired_tags & actual_tags:
        score += 6

    doc_type = str(evidence.get("doc_type") or "")
    if doc_type == "resume":
        score += 3
    elif doc_type == "cover_letter":
        score += 2
    if len(str(evidence.get("text") or "")) > 500:
        score -= 1
    return score


def select_relevant_evidence(
    job: JobDetails,
    context: CandidateContext,
    role_family: str,
    limit: int = 12,
) -> list[dict[str, Any]]:
    job_tokens = tokenize(f"{job.title} {job.description}")
    ranked = sorted(
        context.evidence_bank,
        key=lambda item: (score_evidence(job_tokens, item, role_family), item.get("strength") == "strong"),
        reverse=True,
    )
    selected = [item for item in ranked if score_evidence(job_tokens, item, role_family) > 0][:limit]
    if len(selected) < limit:
        extras = [item for item in ranked if item not in selected and item.get("strength") == "strong"]
        selected.extend(extras[: max(0, limit - len(selected))])
    return selected[:limit]


def summarize_evidence(relevant_evidence: list[dict[str, Any]]) -> str:
    return "\n".join(f"- {item['evidence_id']}: {item['text']}" for item in relevant_evidence)


def make_client() -> OpenAI:
    if not Config.OPENAI_API_KEY:
        raise SystemExit("Missing OPENAI_API_KEY in environment or .env")
    if not Config.OPENAI_FINETUNED_MODEL:
        raise SystemExit("Missing OPENAI_FINETUNED_MODEL in environment or .env")
    return OpenAI(api_key=Config.OPENAI_API_KEY)


def read_message_text(message: Any) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
            else:
                parts.append(str(getattr(part, "text", "")))
        return "".join(parts)
    return str(content or "")


def generate_text_completion(
    client: OpenAI,
    *,
    system_prompt: str,
    user_prompt: str,
    max_completion_tokens: int,
    temperature: float,
) -> str:
    response = client.chat.completions.create(
        model=Config.OPENAI_FINETUNED_MODEL,
        temperature=temperature,
        max_completion_tokens=max_completion_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return read_message_text(response.choices[0].message).strip()


def infer_skill_labels(job: JobDetails) -> list[str]:
    job_text = normalize_match_text(f"{job.title} {job.description}")
    scored_labels: list[tuple[int, str]] = []
    for label, keywords in SKILL_CATEGORY_CANDIDATES:
        score = sum(job_text.count(keyword) for keyword in keywords)
        scored_labels.append((score, label))

    labels: list[str] = []
    seen_slots: set[str] = set()
    for score, label in sorted(scored_labels, reverse=True):
        if score <= 0:
            continue
        slot = software_engineering_skill_slot(label)
        if slot in seen_slots:
            continue
        labels.append(label)
        seen_slots.add(slot)

    for fallback in DEFAULT_SKILL_LABELS:
        slot = software_engineering_skill_slot(fallback)
        if fallback not in labels and slot not in seen_slots:
            labels.append(fallback)
            seen_slots.add(slot)
    return labels[:4]


def software_engineering_skill_slot(label: str) -> str:
    normalized_label = normalize_match_text(label)
    if any(keyword in normalized_label for keyword in ("backend", "api", "language", "framework")):
        return "backend"
    if any(keyword in normalized_label for keyword in ("data", "database", "persistence", "search")):
        return "data"
    if any(keyword in normalized_label for keyword in ("cloud", "devops", "infrastructure")):
        return "cloud"
    return "delivery"


def extract_line_body(text: str) -> str:
    _, separator, remainder = text.partition(":")
    return clean_display_text(remainder if separator else text)


def split_labeled_line(text: str) -> tuple[str, str, str]:
    for separator in (" – ", " — ", ": "):
        if separator in text:
            label, body = text.split(separator, 1)
            return clean_display_text(label), separator, clean_display_text(body)
    return "", ": ", clean_display_text(text)


def infer_writer_competency_labels(job: JobDetails, count: int) -> list[str]:
    job_text = normalize_match_text(f"{job.title} {job.description}")
    labels: list[str] = []
    for fallback, candidates in WRITER_COMPETENCY_SLOT_CANDIDATES[:count]:
        best_label = fallback
        best_score = 0
        for label, keywords in candidates:
            score = sum(job_text.count(keyword) for keyword in keywords)
            if score > best_score:
                best_label = label
                best_score = score
        labels.append(best_label)
    while len(labels) < count:
        labels.append(DEFAULT_WRITER_COMPETENCY_LABELS[len(labels)])
    return labels[:count]


def preferred_resume_lookup(context: CandidateContext, source_file: str) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for item in context.evidence_bank:
        if item.get("source_file") != source_file:
            continue
        source_location = str(item.get("source_location") or "")
        text = clean_display_text(str(item.get("text") or ""))
        if source_location and text:
            lookup[source_location] = text
    return lookup


def required_source_texts(source_lines: dict[str, str], locations: tuple[str, ...]) -> list[str]:
    missing = [location for location in locations if location not in source_lines]
    if missing:
        raise ValueError(f"Missing expected template source lines: {', '.join(missing)}")
    return [source_lines[location] for location in locations]


def software_engineering_skill_body_for_label(
    label: str,
    source_lines: dict[str, str],
    support_source_lines: dict[str, str],
) -> str:
    slot = software_engineering_skill_slot(label)
    if slot == "backend":
        return extract_line_body(source_lines["skills/paragraph_13"])
    if slot == "data":
        body = extract_line_body(source_lines["skills/paragraph_15"])
        if "alembic" not in normalize_match_text(body):
            body = body.replace("schema design; ", "schema design; Alembic migrations; ")
            if "alembic" not in normalize_match_text(body):
                support_body = extract_line_body(support_source_lines["skills/paragraph_14"])
                if "alembic" in normalize_match_text(support_body):
                    body = f"{body}; Alembic migrations"
        return clean_display_text(body)
    if slot == "cloud":
        return extract_line_body(source_lines["skills/paragraph_14"])
    body = extract_line_body(source_lines["skills/paragraph_16"])
    if "bats" not in normalize_match_text(body):
        body = body.replace("Pytest (unit/integration testing)", "Pytest (unit/integration testing), BATS")
    return clean_display_text(body)


def join_phrases(items: list[str]) -> str:
    if not items:
        return "software engineering"
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def build_software_engineering_resume_summary(job: JobDetails) -> str:
    job_text = normalize_match_text(f"{job.title} {job.description}")
    infra_score = sum(
        job_text.count(token)
        for token in ("infrastructure", "platform", "reliability", "site reliability", "devops", "cloud")
    )
    data_score = sum(
        job_text.count(token)
        for token in ("data", "database", "databases", "etl", "pipeline", "pipelines", "sql", "storage")
    )
    api_score = sum(
        job_text.count(token)
        for token in ("api", "apis", "integration", "integrations", "service", "services")
    )

    if infra_score >= 3 and infra_score > data_score:
        focus = "backend services, data pipelines, and cloud infrastructure"
    elif api_score > 0:
        focus = "backend services, REST APIs, and data pipelines"
    else:
        focus = "backend services and data pipelines"
    return f"Software engineer with 6+ years of experience building {focus}."


def normalize_cover_letter_paragraphs(paragraphs: list[str]) -> list[str]:
    normalized: list[str] = []
    for paragraph in paragraphs:
        cleaned = clean_display_text(paragraph)
        if cleaned and cleaned[-1] not in ".!?":
            cleaned += "."
        normalized.append(cleaned)
    return normalized


def build_software_engineering_resume_content(
    context: CandidateContext,
    template_config: TemplateConfig,
    job: JobDetails,
) -> tuple[list[str], str, list[str], list[str]]:
    source_lines = preferred_resume_lookup(context, template_config.preferred_resume_source_file)
    support_source_lines = preferred_resume_lookup(context, SOFTWARE_ENGINEERING_SKILL_SUPPORT_SOURCE_FILE)
    skill_labels = infer_skill_labels(job)
    skills_lines = [
        f"{label} {software_engineering_skill_body_for_label(label, source_lines, support_source_lines)}"
        for label in skill_labels
    ]
    professional_development_body = source_lines[template_config.professional_development_body_source]
    project_bullets = required_source_texts(source_lines, template_config.project_bullet_sources)
    senior_experience_bullets = required_source_texts(source_lines, template_config.senior_experience_bullet_sources)
    return skills_lines, professional_development_body, project_bullets, senior_experience_bullets


def build_customer_facing_resume_content(
    _: CandidateContext,
    template_config: TemplateConfig,
    _role_family: str,
) -> tuple[list[str], str, list[str], list[str]]:
    return extract_template_resume_content(APPLICATION_MATERIALS_DIR, template_config)


def build_technical_writing_resume_content(
    _: CandidateContext,
    template_config: TemplateConfig,
    job: JobDetails,
) -> tuple[list[str], str, list[str], list[str]]:
    skills_lines, professional_development_body, project_bullets, senior_experience_bullets = extract_template_resume_content(
        APPLICATION_MATERIALS_DIR,
        template_config,
    )
    labels = infer_writer_competency_labels(job, len(skills_lines))
    rewritten_lines: list[str] = []
    for line, label in zip(skills_lines, labels):
        _, separator, body = split_labeled_line(line)
        rewritten_lines.append(f"{label}{separator}{body}")
    return rewritten_lines, professional_development_body, project_bullets, senior_experience_bullets


def build_stable_resume_content(
    context: CandidateContext,
    template_config: TemplateConfig,
    role_family: str,
    job: JobDetails,
) -> tuple[list[str], str, list[str], list[str]]:
    if role_family == "software_engineering":
        return build_software_engineering_resume_content(context, template_config, job)
    if role_family == "technical_writing":
        return build_technical_writing_resume_content(context, template_config, job)
    return build_customer_facing_resume_content(context, template_config, role_family)


def generate_resume_summary(
    client: OpenAI,
    job: JobDetails,
    context: CandidateContext,
    relevant_evidence: list[dict[str, Any]],
    role_family: str,
) -> str:
    if role_family == "software_engineering":
        return build_software_engineering_resume_summary(job)

    family_phrase = {
        "software_engineering": "backend and platform software engineering",
        "solutions_engineering": "customer-facing technical and solutions work",
        "technical_support_engineering": "technical support and troubleshooting",
        "technical_writing": "technical writing and documentation",
    }[role_family]
    return clean_display_text(
        generate_text_completion(
            client,
            system_prompt="You write one-line factual resume summaries for Arthur Vargas using only supplied evidence.",
            user_prompt=(
                f"Write one sentence under 18 words for Arthur Vargas's resume summary tailored to {job.company_name} - {job.title}.\n"
                f"Target role family: {role_family} ({family_phrase}).\n"
                f"Candidate overview: {context.canonical_profile['candidate_overview']['professional_identity']}\n"
                f"Relevant evidence:\n{summarize_evidence(relevant_evidence[:4])}\n"
                "Return only the sentence."
            ),
            max_completion_tokens=60,
            temperature=0.2,
        )
    )


def first_sentences(text: str, count: int) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", clean_display_text(text))
    selected = [sentence for sentence in sentences if sentence][:count]
    return " ".join(selected)


def get_evidence_text(context: CandidateContext, preferred_ids: tuple[str, ...]) -> str:
    evidence_by_id = {
        str(item.get("evidence_id") or ""): clean_display_text(str(item.get("text") or ""))
        for item in context.evidence_bank
    }
    for evidence_id in preferred_ids:
        text = evidence_by_id.get(evidence_id)
        if text:
            return text
    raise ValueError(f"Missing expected evidence IDs: {preferred_ids}")


def build_software_engineering_cover_letter(job: JobDetails, context: CandidateContext) -> CoverLetterContent:
    skill_labels = infer_skill_labels(job)

    def skill_phrase_from_label(label: str) -> str:
        normalized_label = normalize_match_text(label)
        if "backend" in normalized_label or "api" in normalized_label:
            return "Python backend systems"
        if "data" in normalized_label or "persistence" in normalized_label:
            return "data modeling and persistence"
        if "cloud" in normalized_label or "infrastructure" in normalized_label:
            return "cloud infrastructure"
        return "delivery automation"

    emphasis_phrases: list[str] = []
    for label in skill_labels[:3]:
        phrase = skill_phrase_from_label(label)
        if phrase not in emphasis_phrases:
            emphasis_phrases.append(phrase)

    opening = (
        f"I am interested in the {job.title} role at {job.company_name}. "
        "My background includes six years of building backend systems, REST APIs, web applications, and data pipelines. "
        f"I am particularly drawn to roles where I can apply strengths in {join_phrases(emphasis_phrases)}."
    )
    backend = (
        "As a Senior Software Engineer at IQVIA, I used Python on a daily basis and built high-throughput pipelines, "
        "web applications, REST APIs, and containerized services for internal research teams processing next-generation sequencing data. "
        "Those systems integrated internal databases, external APIs, and network storage, and produced QC and reporting datasets for downstream services and users. "
        "I also used workflow management tooling like Nextflow and AWS ECS to orchestrate containers across local HPC and AWS environments."
    )
    delivery = (
        "As a development lead, I managed projects from early prototyping through iterative delivery. "
        "One example was a Python CLI application that automated a critical QC workflow by combining laboratory-system data with project-management data, "
        "using Pydantic, relational databases, and existing tooling to accelerate delivery while incorporating end-user feedback over multiple sprints. "
        "Across projects, I also configured CI/CD automation in AWS and Azure Devops, including immutable Docker image tagging and semantic versioning for release traceability."
    )
    growth = (
        "Since my last full-time role, I have kept my skills sharp by building projects and deepening my AI tooling knowledge through recent work on RAG pipelines, vector databases, and multi-agent orchestration."
    )
    closing = (
        f"Thank you for considering my application for the {job.title} role at {job.company_name}. "
        "I would welcome the opportunity to discuss how my background could support your team."
    )
    return CoverLetterContent(body_paragraphs=normalize_cover_letter_paragraphs([opening, backend, delivery, growth, closing]))


def build_customer_facing_cover_letter(
    job: JobDetails,
    context: CandidateContext,
    role_family: str,
) -> CoverLetterContent:
    role_opening = {
        "solutions_engineering": "customer-facing technical work that combines integrations, troubleshooting, and clear technical communication",
        "technical_support_engineering": "technical support work that blends troubleshooting, root-cause analysis, and clear communication with users",
        "technical_writing": "technical writing and documentation work grounded in real engineering systems and user support",
    }[role_family]
    opening = (
        f"I am interested in the {job.title} role at {job.company_name}. "
        "My background combines software engineering depth with documentation, user guidance, implementation support, and cross-functional technical communication. "
        f"I am especially interested in roles centered on {role_opening}."
    )
    body = (
        "In prior roles, I built and supported Python and SQL-based data pipelines, REST APIs, and operational reporting tools that integrated internal databases, network storage, and external APIs. "
        "I also served as a primary technical contact for internal scientific teams, guiding onboarding, usage, troubleshooting, and documentation while working closely with scientists, project managers, and architects to translate real workflows into technical delivery. "
        "That combination of implementation depth, user support, and communication is the part of my background I would bring to a customer-facing technical role."
    )
    closing = (
        "During the time since my last role, I have continued building projects and deepening my AI workflow knowledge around RAG, agent orchestration, and vector databases. "
        f"Thank you for considering my application for the {job.title} role at {job.company_name}. I would welcome the opportunity to discuss how my engineering background, healthcare context, and communication skills could support your team."
    )
    return CoverLetterContent(body_paragraphs=[opening, body, closing])


def build_technical_writing_cover_letter(
    job: JobDetails,
    context: CandidateContext,
) -> CoverLetterContent:
    opening = (
        f"I am interested in the {job.title} role at {job.company_name}. "
        "My background combines software engineering experience with substantial documentation, user guidance, and cross-functional technical communication. "
        "I am especially interested in technical writing roles grounded in real systems, APIs, and developer workflows."
    )
    documentation = (
        "In prior roles, I wrote and maintained user guides, API references, release notes, software design documents, architecture specifications, and troubleshooting materials alongside the systems I was building and supporting. "
        "That work required translating implementation details into documentation that engineers, scientists, and other stakeholders could actually use."
    )
    systems_context = (
        "My engineering background includes Python and SQL-based data pipelines, REST APIs, CLI tools, cloud deployments, and CI/CD workflows, which gives me enough technical context to understand how features behave and where documentation is most needed. "
        "I have also worked closely with product managers, scientists, and QA to gather requirements, clarify edge cases, and document behavior accurately."
    )
    closing = (
        "During the time since my last role, I have continued building projects and deepening my AI workflow knowledge around RAG, agent orchestration, and vector databases. "
        f"Thank you for considering my application for the {job.title} role at {job.company_name}. I would welcome the opportunity to discuss how my writing and engineering background could support your documentation work."
    )
    return CoverLetterContent(body_paragraphs=[opening, documentation, systems_context, closing])


def generate_resume_content(
    client: OpenAI,
    job: JobDetails,
    context: CandidateContext,
    relevant_evidence: list[dict[str, Any]],
    role_family: str,
    template_config: TemplateConfig,
) -> ResumeContent:
    skills_lines, professional_development_body, project_bullets, senior_experience_bullets = build_stable_resume_content(
        context,
        template_config,
        role_family,
        job,
    )
    return ResumeContent(
        summary=generate_resume_summary(client, job, context, relevant_evidence, role_family),
        skills_lines=skills_lines,
        professional_development_body=clean_display_text(professional_development_body),
        project_bullets=project_bullets,
        senior_experience_bullets=senior_experience_bullets,
    )


def generate_cover_letter_content(
    job: JobDetails,
    context: CandidateContext,
    role_family: str,
) -> CoverLetterContent:
    if role_family == "software_engineering":
        return build_software_engineering_cover_letter(job, context)
    if role_family == "technical_writing":
        return build_technical_writing_cover_letter(job, context)
    return build_customer_facing_cover_letter(job, context, role_family)


def save_job_description(job: JobDetails) -> Path:
    GENERATED_JOB_DESCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    file_name = f"{job.company_slug}_{job.job_id}_{slugify(job.title)}.txt"
    path = GENERATED_JOB_DESCRIPTIONS_DIR / file_name
    path.write_text(job.description + "\n", encoding="utf-8")
    return path


def save_metadata(
    output_dir: Path,
    job: JobDetails,
    relevant_evidence: list[dict[str, Any]],
    role_family: str,
    template_config: TemplateConfig,
) -> None:
    payload = {
        "company_name": job.company_name,
        "company_slug": job.company_slug,
        "job_id": job.job_id,
        "job_title": job.title,
        "job_location": job.location,
        "source_url": job.source_url,
        "normalized_source_url": job.normalized_source_url,
        "absolute_url": job.absolute_url,
        "generation_role_family": role_family,
        "resume_template": template_config.resume_template_path,
        "cover_letter_template": template_config.cover_letter_template_path,
        "relevant_evidence_ids": [item["evidence_id"] for item in relevant_evidence],
    }
    (output_dir / "metadata.json").write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def generate_for_job(client: OpenAI, context: CandidateContext, url: str) -> Path:
    job = fetch_job_details(url)
    save_job_description(job)

    role_family = infer_generation_role_family(job.title, job.description)
    template_config = template_config_for_role_family(role_family)
    relevant_evidence = select_relevant_evidence(job, context, role_family, limit=8)
    resume_content = generate_resume_content(client, job, context, relevant_evidence, role_family, template_config)
    cover_letter_content = generate_cover_letter_content(job, context, role_family)

    output_dir = GENERATED_DIR / f"{job.company_slug}_{job.job_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    resume_docx_path = output_dir / "resume.docx"
    cover_letter_docx_path = output_dir / "cover_letter.docx"
    resume_text_path = output_dir / "resume.txt"
    cover_letter_text_path = output_dir / "cover_letter.txt"

    resume_doc = render_resume_docx(APPLICATION_MATERIALS_DIR, resume_docx_path, resume_content, template_config)
    cover_letter_doc = render_cover_letter_docx(APPLICATION_MATERIALS_DIR, cover_letter_docx_path, cover_letter_content, template_config)

    resume_text_path.write_text(document_to_text(resume_doc) + "\n", encoding="utf-8")
    cover_letter_text_path.write_text(document_to_text(cover_letter_doc) + "\n", encoding="utf-8")

    save_metadata(output_dir, job, relevant_evidence, role_family, template_config)
    return output_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate tailored resume and cover letter outputs for matched jobs.")
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        help="Job URL to process. Repeat to process multiple URLs. Defaults to the two seed URLs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    urls = tuple(args.urls) if args.urls else DEFAULT_TEST_URLS
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_JOB_DESCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)

    client = make_client()
    context = load_candidate_context()

    for url in urls:
        output_dir = generate_for_job(client, context, url)
        print(output_dir)


if __name__ == "__main__":
    try:
        main()
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise SystemExit(str(exc))