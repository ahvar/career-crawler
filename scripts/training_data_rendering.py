from __future__ import annotations

import re
from typing import Any


def summarize_sentence(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(".,;:") + "..."


def brief_job_focus(job: Any) -> str:
    highlights = []
    if job.skill_tags:
        highlights.append("skills like " + ", ".join(job.skill_tags[:4]).replace("_", " "))
    if job.requirements:
        highlights.append("requirements around " + summarize_sentence(job.requirements[0], 16))
    elif job.responsibilities:
        highlights.append("work centered on " + summarize_sentence(job.responsibilities[0], 16))
    return "; ".join(highlights)


def evidence_lines(evidence_items: list[dict[str, Any]]) -> str:
    lines = []
    for item in evidence_items:
        lines.append(
            f"- {item['evidence_id']} [{item['evidence_type']}, {item['strength']}]: {item['normalized_summary']}"
        )
    return "\n".join(lines)


def build_system_prompt(task_type: str) -> str:
    if task_type == "cover_letter":
        return (
            "You write tailored cover letters for Arthur Vargas. Stay factual, use only the supplied evidence, "
            "keep a professional but human tone, and avoid inventing experience."
        )
    return (
        "You write tailored resume content for Arthur Vargas. Stay factual, use only the supplied evidence, "
        "favor concise accomplishment-oriented bullets, and do not invent tools, dates, or outcomes."
    )


def build_user_message(
    job: Any,
    canonical_profile: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    task_type: str,
    variant_name: str,
) -> str:
    overview = canonical_profile["candidate_overview"]["professional_identity"]
    requirements = (
        "\n".join(f"- {line}" for line in job.requirements[:5])
        or "- Refer to the role summary and responsibilities."
    )
    responsibilities = (
        "\n".join(f"- {line}" for line in job.responsibilities[:5])
        or "- Refer to the job description summary."
    )
    return (
        f"Task: Write a tailored {task_type.replace('_', ' ')} for this job.\n"
        f"Variant: {variant_name}\n"
        f"Candidate overview: {overview}\n"
        f"Target role family: {job.role_family}\n"
        f"Job title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Job description summary: {summarize_sentence(job.summary, 80)}\n"
        f"Key responsibilities:\n{responsibilities}\n"
        f"Key requirements:\n{requirements}\n"
        f"Relevant evidence:\n{evidence_lines(evidence_items)}"
    )


def role_intro(job: Any) -> str:
    mapping = {
        "software_engineering": "building backend systems, APIs, and data pipelines",
        "technical_support": "troubleshooting production issues and supporting users through technical problems",
        "solutions_engineering": "partnering with stakeholders and translating technical complexity into practical solutions",
        "data_engineering": "building data pipelines and dependable analytics infrastructure",
        "bioinformatics": "developing bioinformatics pipelines and regulated healthcare software",
    }
    return mapping.get(job.role_family, "building dependable software systems")


def rephrase_evidence_for_cover_letter(item: dict[str, Any]) -> str:
    text = item["text"].strip()
    text = re.sub(r"\s+", " ", text)
    text = text.rstrip(".")
    if text.startswith("I "):
        return text + "."
    if text.startswith(("Built ", "Developed ", "Designed ", "Implemented ", "Led ")):
        return f"In recent work, I {text[0].lower() + text[1:]}. "
    return f"My background includes work where I {text[0].lower() + text[1:]}. "


def build_cover_letter(job: Any, evidence_items: list[dict[str, Any]], variant_name: str) -> str:
    top = evidence_items[:3]
    opening_map = {
        "direct": f"I am interested in the {job.title} role at {job.company}. My background includes six years of {role_intro(job)}.",
        "mission": f"I am interested in the {job.title} role at {job.company} because the role's focus on {brief_job_focus(job)} aligns with the kind of work I want to keep doing.",
        "technical": f"I am applying for the {job.title} role at {job.company}. My experience is strongest where Python, cloud infrastructure, and operationally important systems meet.",
        "collaborative": f"I am interested in the {job.title} opportunity at {job.company}. My background combines software engineering depth with documentation, cross-functional collaboration, and support for internal users.",
    }
    body = " ".join(rephrase_evidence_for_cover_letter(item) for item in top)
    focus = brief_job_focus(job)
    closing_map = {
        "direct": f"I would welcome the opportunity to bring that experience to {job.company}, especially in a role centered on {focus}. Thank you for your consideration.",
        "mission": f"I am especially motivated by opportunities where strong engineering can support meaningful outcomes, and {job.company}'s needs in {focus} stand out to me. Thank you for considering my application.",
        "technical": f"I believe that mix of backend engineering, deployment work, and careful execution would translate well to {job.company}'s needs. Thank you for your consideration.",
        "collaborative": f"I would value the chance to support {job.company} with both technical execution and clear collaboration across teams. Thank you for considering my application.",
    }
    return "\n\n".join([opening_map[variant_name], body, closing_map[variant_name]])


def build_resume_summary(job: Any, variant_name: str) -> str:
    summary_map = {
        "backend": f"Software engineer with 6+ years of experience building backend services, data pipelines, and cloud deployments aligned with {job.title} work.",
        "data": f"Software engineer with 6+ years of experience building ETL workflows, operational reporting tools, and Python-based data systems relevant to {job.title} work.",
        "bioinformatics": f"Software engineer with 6+ years of experience building bioinformatics pipelines, regulated clinical software, and backend services for genomics workflows.",
        "support": f"Software engineer with 6+ years of experience spanning production support, troubleshooting, internal-user guidance, and Python-based tooling.",
    }
    return summary_map[variant_name]


def collect_resume_skills(job: Any, evidence_items: list[dict[str, Any]]) -> str:
    tags = []
    for item in evidence_items:
        tags.extend(item.get("skill_tags", []))
    ordered = []
    for tag in job.skill_tags + sorted(set(tags)):
        if tag not in ordered:
            ordered.append(tag)
    display = [tag.replace("_", " ") for tag in ordered[:10]]
    return "- " + ", ".join(display)


def format_bullet(item: dict[str, Any]) -> str:
    text = item["text"].strip()
    text = re.sub(r"\s+", " ", text)
    if not text.startswith("- "):
        text = "- " + text
    return text


def build_resume_output(job: Any, evidence_items: list[dict[str, Any]], variant_name: str) -> str:
    summary = build_resume_summary(job, variant_name)
    skills = collect_resume_skills(job, evidence_items)
    experience_bullets = [format_bullet(item) for item in evidence_items[:4]]
    project_bullets = [format_bullet(item) for item in evidence_items[4:6]]

    lines = [
        "Arthur Vargas",
        summary,
        "",
        "SELECTED SKILLS",
        skills,
        "",
        "EXPERIENCE HIGHLIGHTS",
        *experience_bullets,
    ]
    if project_bullets:
        lines.extend(["", "PROJECT HIGHLIGHTS", *project_bullets])
    lines.extend(
        [
            "",
            "EDUCATION & DEVELOPMENT",
            "- B.S. Biology, North Carolina State University",
            "- Parsity AI Accelerator Program (in progress, expected 2026)",
        ]
    )
    return "\n".join(lines)


def cover_letter_variants_for_job(job: Any) -> list[str]:
    base = ["direct", "technical", "collaborative", "mission"]
    if job.role_family in {"technical_support", "solutions_engineering"}:
        return ["collaborative", "direct", "mission", "technical"]
    if job.role_family in {"bioinformatics", "data_engineering"}:
        return ["technical", "direct", "mission", "collaborative"]
    return base


def resume_variants_for_job(job: Any) -> list[str]:
    if job.role_family == "technical_support":
        return ["support", "backend", "data", "bioinformatics"]
    if job.role_family == "bioinformatics":
        return ["bioinformatics", "backend", "data", "support"]
    if job.role_family == "data_engineering":
        return ["data", "backend", "bioinformatics", "support"]
    return ["backend", "data", "bioinformatics", "support"]