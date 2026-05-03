from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from job_details import JobDetails


DERIVED_PROFILE_DIR = ROOT / "derived_profile"


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


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


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