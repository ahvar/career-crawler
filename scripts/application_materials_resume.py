from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APPLICATION_MATERIALS_DIR = ROOT / "application_materials"

from candidate_evidence import (
    DEFAULT_SKILL_LABELS,
    DEFAULT_WRITER_COMPETENCY_LABELS,
    SKILL_CATEGORY_CANDIDATES,
    SOFTWARE_ENGINEERING_SKILL_SUPPORT_SOURCE_FILE,
    WRITER_COMPETENCY_SLOT_CANDIDATES,
    CandidateContext,
    summarize_evidence,
)
from config import Config
from application_materials_templates import ResumeContent, TemplateConfig, extract_template_resume_content
from job_details import JobDetails


def clean_display_text(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


def normalize_match_text(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[_/|]+", " ", lowered)
    lowered = re.sub(r"[^a-z0-9+&.-]+", " ", lowered)
    return " ".join(lowered.split())


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


def build_software_engineering_resume_summary(job: JobDetails) -> str:
    job_text = normalize_match_text(f"{job.title} {job.description}")
    infra_score = sum(job_text.count(token) for token in ("infrastructure", "platform", "reliability", "site reliability", "devops", "cloud"))
    data_score = sum(job_text.count(token) for token in ("data", "database", "databases", "etl", "pipeline", "pipelines", "sql", "storage"))
    api_score = sum(job_text.count(token) for token in ("api", "apis", "integration", "integrations", "service", "services"))

    if infra_score >= 3 and infra_score > data_score:
        focus = "backend services, data pipelines, and cloud infrastructure"
    elif api_score > 0:
        focus = "backend services, REST APIs, and data pipelines"
    else:
        focus = "backend services and data pipelines"
    return f"Software engineer with 6+ years of experience building {focus}."


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
    client: OpenAI | None,
    job: JobDetails,
    context: CandidateContext,
    relevant_evidence: list[dict[str, Any]],
    role_family: str,
) -> str:
    if role_family == "software_engineering":
        return build_software_engineering_resume_summary(job)

    if client is None:
        raise ValueError("OpenAI client is required for non-software-engineering resume summary generation.")

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


def generate_resume_content(
    client: OpenAI | None,
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