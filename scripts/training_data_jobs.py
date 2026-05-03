from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

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
        if any(
            marker in lower
            for marker in [
                "key responsibilities",
                "main responsibilities",
                "what you’ll do",
                "what you'll do",
                "job description",
            ]
        ):
            current = "responsibilities"
            continue
        if any(
            marker in lower
            for marker in [
                "requirements",
                "qualifications",
                "required experience",
                "required skills",
                "what you need",
                "desired characteristics",
            ]
        ):
            current = "requirements"
            continue
        if current == "responsibilities":
            responsibilities.append(paragraph)
        elif current == "requirements":
            requirements.append(paragraph)
    return responsibilities[:10], requirements[:10]


def load_job_descriptions(*, root: Path, job_description_dirs: list[Path]) -> list[JobDescription]:
    jobs = []
    for directory in job_description_dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.docx")):
            paragraphs = parse_docx(path)
            title = infer_title(paragraphs, path.stem)
            company = infer_company(paragraphs, path.stem)
            full_text = " ".join(paragraphs)
            responsibilities, requirements = split_sections(paragraphs)
            summary = " ".join(paragraphs[1:6])
            jobs.append(
                JobDescription(
                    source_file=str(path.relative_to(root)),
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