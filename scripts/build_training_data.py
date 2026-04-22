#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DERIVED_DIR = ROOT / "derived_profile"
JOB_DESCRIPTION_DIR = DERIVED_DIR / "job_descriptions"
TRAINING_DIR = ROOT / "training_data"
OUTPUT_PATH = TRAINING_DIR / "application_writing_training.jsonl"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
BASE_MODEL = "gpt-4o-mini-2024-07-18"

ROLE_KEYWORDS = {
    "software_engineering": ["backend", "software engineer", "api", "microservice", "python", "serverless"],
    "technical_support": ["support", "root cause", "production issues", "on-call", "debug", "incident"],
    "solutions_engineering": ["solutions engineer", "customer", "partner", "pre-sales", "stakeholder", "implementation"],
    "data_engineering": ["data engineer", "etl", "elt", "airflow", "data lake", "pipeline orchestration", "warehouse"],
    "bioinformatics": ["bioinformatics", "genomics", "sequencing", "clinical", "diagnostics"],
}

SKILL_KEYWORDS = {
    "python": ["python"],
    "aws": ["aws", "lambda", "ecs", "ec2", "ecr", "s3", "iam", "cloudwatch", "kinesis"],
    "docker": ["docker", "container"],
    "ci_cd": ["ci/cd", "codepipeline", "codebuild", "github workflows", "azure devops"],
    "sql": ["sql", "mysql", "postgresql", "postgres", "sqlite", "dynamodb"],
    "flask": ["flask"],
    "nextflow": ["nextflow"],
    "support": ["support", "debug", "root cause", "troubleshooting", "postman", "on-call"],
    "writing": ["documentation", "communication", "user guides", "manuals", "sops"],
    "ai_ml": ["rag", "vector", "llm", "agent"],
}


@dataclass
class JobDescription:
    source_file: str
    title: str
    company: str
    paragraphs: list[str]
    role_family: str
    skill_tags: list[str]
    summary: str
    responsibilities: list[str]
    requirements: list[str]


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_docx(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    paragraphs = []
    for para in root.findall(".//w:p", NS):
        texts = [node.text or "" for node in para.findall(".//w:t", NS)]
        text = normalize_whitespace("".join(texts))
        if text:
            paragraphs.append(text)
    return paragraphs


def infer_company(paragraphs: list[str], fallback_name: str) -> str:
    for paragraph in paragraphs[:15]:
        if paragraph.startswith("ABOUT "):
            about_value = paragraph.replace("ABOUT ", "").strip()
            if about_value.upper() not in {"THE ROLE", "THE TEAM"}:
                return about_value.title()
        match = re.search(r"Who is ([A-Z][A-Za-z0-9& .'-]+)\?", paragraph)
        if match:
            return match.group(1).strip()
        match = re.search(r"About ([A-Z][A-Za-z0-9& .'-]+)", paragraph)
        if match:
            return match.group(1).strip()
        match = re.search(r"At ([A-Z][A-Za-z0-9& .'-]+),", paragraph)
        if match:
            return match.group(1).strip()
        match = re.search(r",\s*([A-Z][A-Za-z0-9& .'-]{2,60}?)\s+is\b", paragraph)
        if match:
            return match.group(1).strip()
        match = re.search(r"^([A-Z][A-Za-z0-9& .'-]{2,60}?)\s+is\b", paragraph)
        if match:
            return match.group(1).strip()
        match = re.search(r"^([A-Z][A-Za-z0-9& .'-]{2,60}?)\s+(helps|empowers|builds|exists|offers|participates)\b", paragraph)
        if match:
            return match.group(1).strip()
        match = re.search(r"^([A-Z][A-Za-z0-9& .'-]{2,60}?),\s+a\b", paragraph)
        if match:
            return match.group(1).strip()
        match = re.search(r"^([A-Z][A-Za-z0-9& .'-]{2,60}?)\s+needs a\b", paragraph)
        if match:
            return match.group(1).strip()
        if "posthog" in paragraph.lower():
            return "PostHog"
        if "blenderbox" in paragraph.lower():
            return "Blenderbox"
        if "bestow" in paragraph.lower():
            return "Bestow"
        if "visa technology & operations llc" in paragraph.lower():
            return "Visa"
        if "cesiumastro" in paragraph.lower():
            return "CesiumAstro"
        if "gm av simulation" in paragraph.lower() or " gm " in f" {paragraph.lower()} ":
            return "GM"
    cleaned = re.sub(r"\.docx$", "", fallback_name, flags=re.IGNORECASE)
    cleaned = cleaned.replace("_", " ")
    if cleaned.lower().startswith("jd"):
        return "Unknown Company"
    return cleaned


def infer_title(paragraphs: list[str], fallback_name: str) -> str:
    cleaned = re.sub(r"\.docx$", "", fallback_name, flags=re.IGNORECASE).replace("_", " ")
    role_words = ("engineer", "developer", "lead", "scientist", "architect")
    for paragraph in paragraphs[:15]:
        for pattern in [
            r"We are seeking an experienced ([A-Z][A-Za-z0-9 ./&()\-]+?) to",
            r"As a ([A-Z][A-Za-z0-9 ./&()\-]+?) on",
            r"needs a ([A-Z][A-Za-z0-9 ./&()\-]+?) in",
            r"The ([A-Z][A-Za-z0-9 ./&()\-]+?) will",
        ]:
            match = re.search(pattern, paragraph)
            if match:
                candidate = match.group(1).strip()
                if any(word in candidate.lower() for word in role_words):
                    return candidate
    for paragraph in paragraphs[:12]:
        lower = paragraph.lower()
        if any(word in lower for word in role_words) and len(paragraph) <= 100:
            return paragraph.strip()
    return cleaned


def infer_role_family(title: str, text: str) -> str:
    lower = text.lower()
    title_lower = title.lower()
    scores: dict[str, int] = {}
    for role, keywords in ROLE_KEYWORDS.items():
        scores[role] = sum(1 for keyword in keywords if keyword in lower)
        scores[role] += 2 * sum(1 for keyword in keywords if keyword in title_lower)
    best_role = max(scores, key=scores.get)
    return best_role if scores[best_role] > 0 else "software_engineering"


def infer_skill_tags(text: str) -> list[str]:
    lower = text.lower()
    tags = []
    for tag, keywords in SKILL_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            tags.append(tag)
    return sorted(set(tags))


def split_sections(paragraphs: list[str]) -> tuple[list[str], list[str]]:
    responsibilities = []
    requirements = []
    current = None
    for paragraph in paragraphs:
        lower = paragraph.lower()
        if any(marker in lower for marker in ["key responsibilities", "main responsibilities", "what you’ll do", "what you'll do", "job description"]):
            current = "responsibilities"
            continue
        if any(marker in lower for marker in ["requirements", "qualifications", "required experience", "required skills", "what you need", "desired characteristics"]):
            current = "requirements"
            continue
        if current == "responsibilities":
            responsibilities.append(paragraph)
        elif current == "requirements":
            requirements.append(paragraph)
    return responsibilities[:10], requirements[:10]


def load_job_descriptions() -> list[JobDescription]:
    jobs = []
    for path in sorted(JOB_DESCRIPTION_DIR.glob("*.docx")):
        paragraphs = parse_docx(path)
        title = infer_title(paragraphs, path.stem)
        company = infer_company(paragraphs, path.stem)
        full_text = " ".join(paragraphs)
        responsibilities, requirements = split_sections(paragraphs)
        summary = " ".join(paragraphs[1:6])
        jobs.append(
            JobDescription(
                source_file=str(path.relative_to(ROOT)),
                title=title,
                company=company,
                paragraphs=paragraphs,
                role_family=infer_role_family(title, full_text),
                skill_tags=infer_skill_tags(full_text),
                summary=summary,
                responsibilities=responsibilities,
                requirements=requirements,
            )
        )
    return jobs


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def score_evidence(item: dict[str, Any], job: JobDescription) -> int:
    score = 0
    if job.role_family in item.get("role_tags", []):
        score += 5
    for skill in job.skill_tags:
        if skill in item.get("skill_tags", []):
            score += 3
    if item.get("strength") == "strong":
        score += 2
    if item.get("is_quantified"):
        score += 1
    if job.role_family == "bioinformatics" and "genomics" in item.get("domain_tags", []):
        score += 3
    if job.role_family == "data_engineering" and any(tag in item.get("skill_tags", []) for tag in ["sql", "python", "aws"]):
        score += 2
    if job.role_family == "technical_support":
        if "technical_support" in item.get("role_tags", []):
            score += 6
        if any(tag in item.get("skill_tags", []) for tag in ["support", "troubleshooting", "writing"]):
            score += 4
        if "technical support" in item.get("text", "").lower() or "root cause" in item.get("text", "").lower():
            score += 4
    if job.role_family == "solutions_engineering":
        if "solutions_engineering" in item.get("role_tags", []) or "customer_success" in item.get("role_tags", []):
            score += 4
        if any(tag in item.get("skill_tags", []) for tag in ["writing", "support"]):
            score += 2
    return score


def select_evidence(evidence_bank: list[dict[str, Any]], job: JobDescription, limit: int = 8) -> list[dict[str, Any]]:
    ranked = sorted(
        evidence_bank,
        key=lambda item: (score_evidence(item, job), item.get("strength") == "strong", item["evidence_id"]),
        reverse=True,
    )
    chosen = []
    seen = set()
    for item in ranked:
        if score_evidence(item, job) <= 0:
            continue
        key = (item.get("organization_or_project"), item.get("normalized_summary"))
        if key in seen:
            continue
        chosen.append(item)
        seen.add(key)
        if len(chosen) >= limit:
            break
    return chosen


def brief_job_focus(job: JobDescription) -> str:
    highlights = []
    if job.skill_tags:
        highlights.append("skills like " + ", ".join(job.skill_tags[:4]).replace("_", " "))
    if job.requirements:
        highlights.append("requirements around " + summarize_sentence(job.requirements[0], 16))
    elif job.responsibilities:
        highlights.append("work centered on " + summarize_sentence(job.responsibilities[0], 16))
    return "; ".join(highlights)


def summarize_sentence(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(".,;:") + "..."


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


def build_user_message(job: JobDescription, canonical_profile: dict[str, Any], evidence_items: list[dict[str, Any]], task_type: str, variant_name: str) -> str:
    overview = canonical_profile["candidate_overview"]["professional_identity"]
    role_family = job.role_family
    requirements = "\n".join(f"- {line}" for line in job.requirements[:5]) or "- Refer to the role summary and responsibilities."
    responsibilities = "\n".join(f"- {line}" for line in job.responsibilities[:5]) or "- Refer to the job description summary."
    return (
        f"Task: Write a tailored {task_type.replace('_', ' ')} for this job.\n"
        f"Variant: {variant_name}\n"
        f"Candidate overview: {overview}\n"
        f"Target role family: {role_family}\n"
        f"Job title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Job description summary: {summarize_sentence(job.summary, 80)}\n"
        f"Key responsibilities:\n{responsibilities}\n"
        f"Key requirements:\n{requirements}\n"
        f"Relevant evidence:\n{evidence_lines(evidence_items)}"
    )


def role_intro(job: JobDescription) -> str:
    mapping = {
        "software_engineering": "building backend systems, APIs, and data pipelines",
        "technical_support": "troubleshooting production issues and supporting users through technical problems",
        "solutions_engineering": "partnering with stakeholders and translating technical complexity into practical solutions",
        "data_engineering": "building data pipelines and dependable analytics infrastructure",
        "bioinformatics": "developing bioinformatics pipelines and regulated healthcare software",
    }
    return mapping.get(job.role_family, "building dependable software systems")


def build_cover_letter(job: JobDescription, evidence_items: list[dict[str, Any]], variant_name: str) -> str:
    top = evidence_items[:3]
    opening_map = {
        "direct": f"I am interested in the {job.title} role at {job.company}. My background includes six years of {role_intro(job)}.",
        "mission": f"I am interested in the {job.title} role at {job.company} because the role's focus on {brief_job_focus(job)} aligns with the kind of work I want to keep doing.",
        "technical": f"I am applying for the {job.title} role at {job.company}. My experience is strongest where Python, cloud infrastructure, and operationally important systems meet.",
        "collaborative": f"I am interested in the {job.title} opportunity at {job.company}. My background combines software engineering depth with documentation, cross-functional collaboration, and support for internal users.",
    }
    opening = opening_map[variant_name]

    body_sentences = []
    for item in top:
        body_sentences.append(rephrase_evidence_for_cover_letter(item))
    body = " ".join(body_sentences)

    focus = brief_job_focus(job)
    closing_map = {
        "direct": f"I would welcome the opportunity to bring that experience to {job.company}, especially in a role centered on {focus}. Thank you for your consideration.",
        "mission": f"I am especially motivated by opportunities where strong engineering can support meaningful outcomes, and {job.company}'s needs in {focus} stand out to me. Thank you for considering my application.",
        "technical": f"I believe that mix of backend engineering, deployment work, and careful execution would translate well to {job.company}'s needs. Thank you for your consideration.",
        "collaborative": f"I would value the chance to support {job.company} with both technical execution and clear collaboration across teams. Thank you for considering my application.",
    }
    closing = closing_map[variant_name]
    return "\n\n".join([opening, body, closing])


def rephrase_evidence_for_cover_letter(item: dict[str, Any]) -> str:
    text = item["text"].strip()
    text = re.sub(r"\s+", " ", text)
    text = text.rstrip(".")
    if text.startswith("I "):
        return text + "."
    if text.startswith("Built ") or text.startswith("Developed ") or text.startswith("Designed ") or text.startswith("Implemented ") or text.startswith("Led "):
        return f"In recent work, I {text[0].lower() + text[1:]}. "
    return f"My background includes work where I {text[0].lower() + text[1:]}. "


def build_resume_output(job: JobDescription, evidence_items: list[dict[str, Any]], variant_name: str) -> str:
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


def build_resume_summary(job: JobDescription, variant_name: str) -> str:
    summary_map = {
        "backend": f"Software engineer with 6+ years of experience building backend services, data pipelines, and cloud deployments aligned with {job.title} work.",
        "data": f"Software engineer with 6+ years of experience building ETL workflows, operational reporting tools, and Python-based data systems relevant to {job.title} work.",
        "bioinformatics": f"Software engineer with 6+ years of experience building bioinformatics pipelines, regulated clinical software, and backend services for genomics workflows.",
        "support": f"Software engineer with 6+ years of experience spanning production support, troubleshooting, internal-user guidance, and Python-based tooling.",
    }
    return summary_map[variant_name]


def collect_resume_skills(job: JobDescription, evidence_items: list[dict[str, Any]]) -> str:
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


def cover_letter_variants_for_job(job: JobDescription) -> list[str]:
    base = ["direct", "technical", "collaborative", "mission"]
    if job.role_family in {"technical_support", "solutions_engineering"}:
        return ["collaborative", "direct", "mission", "technical"]
    if job.role_family in {"bioinformatics", "data_engineering"}:
        return ["technical", "direct", "mission", "collaborative"]
    return base


def resume_variants_for_job(job: JobDescription) -> list[str]:
    if job.role_family == "technical_support":
        return ["support", "backend", "data", "bioinformatics"]
    if job.role_family == "bioinformatics":
        return ["bioinformatics", "backend", "data", "support"]
    if job.role_family == "data_engineering":
        return ["data", "backend", "bioinformatics", "support"]
    return ["backend", "data", "bioinformatics", "support"]


def build_training_examples(
    canonical_profile: dict[str, Any],
    evidence_bank: list[dict[str, Any]],
    jobs: list[JobDescription],
) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for job in jobs:
        relevant_evidence = select_evidence(evidence_bank, job)
        for variant in cover_letter_variants_for_job(job):
            messages = [
                {"role": "system", "content": build_system_prompt("cover_letter")},
                {"role": "user", "content": build_user_message(job, canonical_profile, relevant_evidence, "cover_letter", variant)},
                {"role": "assistant", "content": build_cover_letter(job, relevant_evidence, variant)},
            ]
            examples.append({"messages": messages})
        for variant in resume_variants_for_job(job):
            messages = [
                {"role": "system", "content": build_system_prompt("resume")},
                {"role": "user", "content": build_user_message(job, canonical_profile, relevant_evidence, "resume", variant)},
                {"role": "assistant", "content": build_resume_output(job, relevant_evidence, variant)},
            ]
            examples.append({"messages": messages})
    return examples


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")


def main() -> None:
    canonical_profile = load_json(DERIVED_DIR / "canonical_profile.json")
    evidence_bank = load_jsonl(DERIVED_DIR / "evidence_bank.jsonl")
    jobs = load_job_descriptions()
    TRAINING_DIR.mkdir(exist_ok=True)
    examples = build_training_examples(canonical_profile, evidence_bank, jobs)
    write_jsonl(OUTPUT_PATH, examples)
    print(f"Wrote {len(examples)} training examples to {OUTPUT_PATH}")
    print(f"Base model target: {BASE_MODEL}")


if __name__ == "__main__":
    main()
