#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
ARCHIVE_DIR = ROOT / "resumes_cov_letters" / "archive"
DERIVED_DIR = ROOT / "derived_profile"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

ROLE_KEYWORDS = {
    "software_engineering": [
        "software engineer",
        "backend",
        "rest api",
        "microservice",
        "web application",
        "python cli",
        "flask",
        "etl",
        "data pipeline",
    ],
    "technical_support": [
        "technical support",
        "troubleshooting",
        "triage",
        "primary technical contact",
        "support materials",
        "onboarding",
        "incident",
        "root cause",
    ],
    "technical_writing": [
        "documentation",
        "user guides",
        "sops",
        "troubleshooting guides",
        "architecture specifications",
        "design",
        "explain complex",
        "writing",
    ],
    "customer_success": [
        "customer",
        "users",
        "end-user",
        "onboarding",
        "guided users",
        "technical contact",
    ],
    "solutions_engineering": [
        "cross-functional",
        "translate end-user needs",
        "integrating",
        "stakeholders",
        "project managers",
        "bioinformaticians",
        "business analysts",
    ],
    "developer_relations_or_support": [
        "internal research teams",
        "internal scientific teams",
        "developer",
        "api",
        "documentation",
        "support contacts",
    ],
}

SKILL_KEYWORDS = {
    "python": ["python"],
    "flask": ["flask"],
    "sql": ["sql", "mysql", "sqlite", "postgresql", "postgres"],
    "sqlalchemy": ["sqlalchemy"],
    "pandas": ["pandas"],
    "numpy": ["numpy"],
    "bash": ["bash"],
    "java": ["java", "groovy"],
    "javascript": ["javascript", "react"],
    "aws": ["aws", "ec2", "ecs", "ecr", "s3", "iam", "codepipeline", "codebuild", "lambda"],
    "docker": ["docker", "containerized", "containers"],
    "ci_cd": ["ci/cd", "azure devops", "codepipeline", "codebuild", "semantic versioning", "build automation"],
    "nextflow": ["nextflow"],
    "bioinformatics": ["genomics", "bioinformatics", "sequencing", "illumina", "ion torrent", "sam/bam/vcf", "q30"],
    "elasticsearch": ["elasticsearch", "kibana"],
    "redis": ["redis", "redis queue"],
    "testing": ["pytest", "bats", "coverage", "test-driven", "validation testing", "unit testing", "integration tests"],
    "technical_documentation": ["documentation", "user guides", "sops", "architecture specifications", "confluence", "manuals"],
    "troubleshooting": ["troubleshooting", "root cause", "triage", "support"],
    "leadership": ["led", "tech lead", "coordinated", "planning", "code reviews"],
    "rag_and_llms": ["rag", "vector databases", "agent orchestration", "multi-agent", "openai", "fine-tuning", "llm"],
}

DOMAIN_KEYWORDS = {
    "genomics": ["genomic", "genomics", "sequencing", "bioinformatics", "next-generation sequencing", "ngs"],
    "healthcare": ["clinical", "healthcare", "oncology", "diagnostics", "patient", "medical device", "clia", "fda"],
    "saas_internal_tools": ["saas", "internal research teams", "internal scientific teams", "internal database", "lims"],
    "developer_tools": ["cli", "build pipelines", "yaml pipeline templates", "automation"],
    "ai_ml": ["rag", "vector databases", "llm", "multi-agent", "fine-tuning"],
}

CANONICAL_SKILL_IDS = {
    "python": "skill_python",
    "flask": "skill_flask",
    "sql": "skill_sql_and_relational_databases",
    "sqlalchemy": "skill_sqlalchemy",
    "pandas": "skill_pandas",
    "numpy": "skill_numpy",
    "bash": "skill_bash",
    "java": "skill_java_and_groovy",
    "javascript": "skill_javascript_and_react",
    "aws": "skill_aws",
    "docker": "skill_docker",
    "ci_cd": "skill_ci_cd",
    "nextflow": "skill_nextflow",
    "bioinformatics": "skill_bioinformatics_pipeline_engineering",
    "elasticsearch": "skill_elasticsearch",
    "redis": "skill_redis_queue",
    "testing": "skill_testing_and_quality",
    "technical_documentation": "skill_technical_documentation",
    "troubleshooting": "skill_troubleshooting_and_support",
    "leadership": "skill_technical_leadership",
    "rag_and_llms": "skill_rag_and_llm_workflows",
}


@dataclass
class Paragraph:
    index: int
    text: str


@dataclass
class ParsedDoc:
    source_file: str
    doc_type: str
    paragraphs: list[Paragraph]


@dataclass
class EvidenceRecord:
    evidence_id: str
    source_file: str
    doc_type: str
    source_location: str
    text: str
    normalized_summary: str
    evidence_type: str
    role_tags: list[str]
    skill_tags: list[str]
    domain_tags: list[str]
    strength: str
    is_quantified: bool
    dates_mentioned: list[str]
    organization_or_project: str | None
    canonical_entity_refs: list[str] = field(default_factory=list)
    notes: str = ""

    def as_json(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_file": self.source_file,
            "doc_type": self.doc_type,
            "source_location": self.source_location,
            "text": self.text,
            "normalized_summary": self.normalized_summary,
            "evidence_type": self.evidence_type,
            "role_tags": self.role_tags,
            "skill_tags": self.skill_tags,
            "domain_tags": self.domain_tags,
            "strength": self.strength,
            "is_quantified": self.is_quantified,
            "dates_mentioned": self.dates_mentioned,
            "organization_or_project": self.organization_or_project,
            "canonical_entity_refs": self.canonical_entity_refs,
            "notes": self.notes,
        }


def parse_docx(path: Path) -> list[Paragraph]:
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    paragraphs: list[Paragraph] = []
    for idx, para in enumerate(root.findall(".//w:p", NS)):
        texts = [node.text or "" for node in para.findall(".//w:t", NS)]
        text = "".join(texts).strip()
        if text:
            paragraphs.append(Paragraph(index=idx, text=normalize_whitespace(text)))
    return paragraphs


def classify_doc_type(path: Path, paragraphs: list[Paragraph]) -> str:
    name = path.name.lower()
    if "resume" in name:
        return "resume"
    if "cover_letter" in name:
        return "cover_letter"
    if "question" in name:
        return "application_qa"
    if any("dear hiring" in p.text.lower() for p in paragraphs):
        return "cover_letter"
    return "other"


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def is_contact_line(text: str) -> bool:
    lower = text.lower()
    return (
        lower.startswith("arthur vargas")
        or lower.startswith("location:")
        or lower.startswith("mobile:")
        or lower.startswith("email:")
        or lower.startswith("linkedin:")
        or lower.startswith("website:")
        or lower.startswith("github")
        or lower.startswith("+1 (")
        or lower.startswith("dear hiring")
        or lower.startswith("sincerely")
        or text.startswith("http://")
        or text.startswith("https://")
        or ("@" in text and " " not in text)
        or lower == "github"
    )


def is_heading(text: str) -> bool:
    if text in {"SUMMARY", "TECHNICAL SKILLS", "RECENT PROFESSIONAL DEVELOPMENT", "PROJECTS", "RECENT PROJECTS", "PROFESSIONAL EXPERIENCE", "EDUCATION", "EDUCATION & PROFESSIONAL DEVELOPMENT"}:
        return True
    return text.isupper() and len(text.split()) <= 6


def is_date_line(text: str) -> bool:
    return bool(re.search(r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+\d{4}", text))


def find_tags(text: str, keyword_map: dict[str, list[str]]) -> list[str]:
    lower = text.lower()
    tags = []
    for tag, keywords in keyword_map.items():
        if any(keyword in lower for keyword in keywords):
            tags.append(tag)
    return sorted(set(tags))


def infer_strength(text: str, evidence_type: str, doc_type: str) -> str:
    lower = text.lower()
    quantified = bool(re.search(r"\b\d", text))
    if evidence_type in {"achievement", "project", "skill_demonstration", "leadership", "customer_interaction"}:
        if quantified or any(k in lower for k in ["decreased", "enabled", "improved", "led", "developed", "implemented", "built", "deployed"]):
            return "strong"
        return "medium"
    if doc_type == "cover_letter":
        return "medium"
    if evidence_type in {"preference", "education"}:
        return "medium"
    return "weak"


def infer_evidence_type(text: str, section: str | None, doc_type: str) -> str:
    lower = text.lower()
    if section == "skills":
        return "skill_demonstration"
    if section == "education":
        return "education"
    if any(k in lower for k in ["led", "coordinated", "tech lead", "planning", "code reviews"]):
        return "leadership"
    if any(k in lower for k in ["guided users", "onboarding", "troubleshooting", "root cause", "primary technical contact", "technical support", "incident management"]):
        return "customer_interaction"
    if any(k in lower for k in ["documentation", "user guides", "manuals", "sops", "architecture specifications", "confluence"]):
        return "writing_sample" if doc_type != "resume" else "skill_demonstration"
    if any(k in lower for k in ["interested in", "looking for", "motivated", "i am applying", "i’m applying", "i'm applying"]):
        return "preference"
    if any(k in lower for k in ["built", "developed", "implemented", "designed", "deployed", "created"]):
        if section == "projects":
            return "project"
        return "achievement"
    if section == "experience":
        return "responsibility"
    return "other"


def summarize_text(text: str, max_words: int = 20) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(".,;:") + "..."


def dates_in_text(text: str) -> list[str]:
    return re.findall(r"(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+\d{4}|(?:19|20)\d{2}", text)


def extract_from_resume(doc: ParsedDoc, start_index: int) -> tuple[list[EvidenceRecord], int]:
    evidence: list[EvidenceRecord] = []
    section: str | None = None
    current_org: str | None = None
    current_project: str | None = None

    for para in doc.paragraphs:
        text = para.text
        if is_contact_line(text):
            continue
        if is_heading(text):
            upper = text.upper()
            if "SKILLS" in upper:
                section = "skills"
            elif "PROJECT" in upper:
                section = "projects"
            elif "EXPERIENCE" in upper:
                section = "experience"
            elif "EDUCATION" in upper:
                section = "education"
            else:
                section = None
            continue
        if is_date_line(text):
            continue
        if "|" in text and section == "experience":
            parts = [p.strip() for p in text.split("|", 1)]
            current_org = parts[0]
            continue
        if section == "projects" and re.search(r"\(\d{4}\)", text):
            current_project = text.split("(", 1)[0].strip()
            continue
        if len(text) < 12:
            continue

        evidence_id = f"ev_{start_index:04d}"
        start_index += 1
        role_tags = find_tags(text, ROLE_KEYWORDS)
        skill_tags = find_tags(text, SKILL_KEYWORDS)
        domain_tags = find_tags(text, DOMAIN_KEYWORDS)
        evidence_type = infer_evidence_type(text, section, doc.doc_type)
        notes = ""
        if current_project:
            notes = f"project_context={current_project}"
        source_location = f"paragraph_{para.index}"
        if section:
            source_location = f"{section}/{source_location}"
        evidence.append(
            EvidenceRecord(
                evidence_id=evidence_id,
                source_file=doc.source_file,
                doc_type=doc.doc_type,
                source_location=source_location,
                text=text,
                normalized_summary=summarize_text(text),
                evidence_type=evidence_type,
                role_tags=role_tags,
                skill_tags=skill_tags,
                domain_tags=domain_tags,
                strength=infer_strength(text, evidence_type, doc.doc_type),
                is_quantified=bool(re.search(r"\b\d", text)),
                dates_mentioned=dates_in_text(text),
                organization_or_project=current_project or current_org,
                notes=notes,
            )
        )
    return evidence, start_index


def extract_from_non_resume(doc: ParsedDoc, start_index: int) -> tuple[list[EvidenceRecord], int]:
    evidence: list[EvidenceRecord] = []
    current_question: str | None = None
    for para in doc.paragraphs:
        raw_text = para.text
        if doc.doc_type == "application_qa":
            prompt, answer = split_prompt_and_answer(raw_text)
            if prompt:
                current_question = prompt
            text = answer or raw_text
        else:
            text = raw_text
        lower = text.lower()
        if is_contact_line(text):
            continue
        if "your resume" in lower or "resume honest" in lower or "for this posting" in lower:
            continue
        if doc.doc_type == "application_qa" and looks_like_prompt(text):
            current_question = text
            continue
        if doc.doc_type == "application_qa" and is_question_only(text):
            current_question = text
            continue
        if doc.doc_type == "cover_letter" and any(
            lower.startswith(prefix)
            for prefix in ["thank you for considering", "please see my resume", "i would welcome an opportunity"]
        ):
            continue
        if len(text) < 25:
            continue
        source_location = f"paragraph_{para.index}"
        if current_question and current_question != text:
            source_location = f"{source_location} | prompt={summarize_text(current_question, 12)}"
        evidence_type = infer_evidence_type(text, None, doc.doc_type)
        role_tags = find_tags(text, ROLE_KEYWORDS)
        skill_tags = find_tags(text, SKILL_KEYWORDS)
        domain_tags = find_tags(text, DOMAIN_KEYWORDS)
        notes = ""
        if doc.doc_type == "cover_letter":
            notes = "Candidate-authored narrative used as style and motivation evidence."
        elif doc.doc_type == "application_qa":
            notes = "Application response; useful for motivations, examples, and writing style."
        evidence.append(
            EvidenceRecord(
                evidence_id=f"ev_{start_index:04d}",
                source_file=doc.source_file,
                doc_type=doc.doc_type,
                source_location=source_location,
                text=text,
                normalized_summary=summarize_text(text),
                evidence_type=evidence_type,
                role_tags=role_tags,
                skill_tags=skill_tags,
                domain_tags=domain_tags,
                strength=infer_strength(text, evidence_type, doc.doc_type),
                is_quantified=bool(re.search(r"\b\d", text)),
                dates_mentioned=dates_in_text(text),
                organization_or_project="IQVIA" if "iqvia" in lower else None,
                notes=notes,
            )
        )
        start_index += 1
    return evidence, start_index


def is_question_only(text: str) -> bool:
    stripped = text.strip()
    return stripped.endswith("?") or stripped.startswith(tuple(str(i) + "." for i in range(1, 10)))


def looks_like_prompt(text: str) -> bool:
    lower = text.lower().strip()
    prompt_starts = (
        "why are you interested",
        "in 3",
        "tell us about",
        "describe a political",
        "describe an engineering tool",
        "what should the requirements.txt",
    )
    return lower.startswith(prompt_starts)


def split_prompt_and_answer(text: str) -> tuple[str | None, str | None]:
    if not text:
        return None, None
    for marker in [")I ", ")At ", ")One ", "?I ", "?At ", "?One ", "?In "]:
        if marker in text:
            left, right = text.split(marker, 1)
            prompt = left + marker[0]
            answer = marker[1:] + right
            return prompt.strip(), answer.lstrip(" )").strip()
    if "?" in text and not text.strip().endswith("?"):
        prompt, answer = text.rsplit("?", 1)
        if answer.strip():
            return prompt.strip() + "?", answer.strip()
    return None, text


def collect_docs() -> list[ParsedDoc]:
    if not ARCHIVE_DIR.exists():
        raise SystemExit(f"Missing source directory: {ARCHIVE_DIR}")
    docs = []
    for path in sorted(ARCHIVE_DIR.rglob("*.docx")):
        if path.name.startswith("~$"):
            continue
        paragraphs = parse_docx(path)
        if not paragraphs:
            raise SystemExit(f"Parsed empty document: {path}")
        docs.append(
            ParsedDoc(
                source_file=str(path.relative_to(ROOT)),
                doc_type=classify_doc_type(path, paragraphs),
                paragraphs=paragraphs,
            )
        )
    return docs


def build_evidence_bank(docs: list[ParsedDoc]) -> list[EvidenceRecord]:
    evidence: list[EvidenceRecord] = []
    next_id = 1
    for doc in docs:
        if doc.doc_type == "resume":
            items, next_id = extract_from_resume(doc, next_id)
        else:
            items, next_id = extract_from_non_resume(doc, next_id)
        evidence.extend(items)

    evidence = [clean_evidence_item(item) for item in evidence]
    evidence = [item for item in evidence if keep_evidence_item(item)]

    for item in evidence:
        item.canonical_entity_refs = infer_canonical_refs(item)
    return evidence


def clean_evidence_item(item: EvidenceRecord) -> EvidenceRecord:
    item.text = re.sub(r"^\([^)]*\)", "", item.text).strip()
    item.text = normalize_whitespace(item.text)
    item.normalized_summary = summarize_text(item.text)
    return item


def keep_evidence_item(item: EvidenceRecord) -> bool:
    lower = item.text.lower().strip()
    if not lower or len(lower) < 20:
        return False
    if is_contact_line(item.text):
        return False
    if looks_like_prompt(item.text) or is_question_only(item.text):
        return False
    if "resume honest" in lower or "for this posting" in lower:
        return False
    return True


def infer_canonical_refs(item: EvidenceRecord) -> list[str]:
    refs: set[str] = set()
    if item.organization_or_project:
        name = item.organization_or_project.lower()
        if name.startswith("iqvia"):
            if "senior software engineer" in item.text.lower() or "global team of 3" in item.text.lower():
                refs.add("exp_iqvia_senior_software_engineer")
            elif "software engineer iii" in item.text.lower():
                refs.add("exp_iqvia_software_engineer_iii")
            elif "software engineer ii" in item.text.lower():
                refs.add("exp_iqvia_software_engineer_ii")
            else:
                refs.add("exp_iqvia")
        if "gene annotator" in name:
            refs.add("proj_gene_annotator")
    lower = item.text.lower()
    if "genexus" in lower or "qc reports" in lower or "project data" in lower:
        refs.add("proj_qc_reporting_cli")
    if "samplesheet" in lower or "clientid" in lower or "projectid" in lower:
        refs.add("proj_samplesheet_parser")
    if "parsity" in lower or "ai accelerator" in lower:
        refs.add("cred_parsity_ai_accelerator")
    if "biology" in lower and "north carolina state university" in lower:
        refs.add("edu_bs_biology_ncsu")
    if "english" in lower and "north carolina state university" in lower:
        refs.add("edu_ba_english_ncsu")
    for skill_tag in item.skill_tags:
        skill_id = CANONICAL_SKILL_IDS.get(skill_tag)
        if skill_id:
            refs.add(skill_id)
    return sorted(refs)


def ids_for_evidence(evidence: list[EvidenceRecord], predicate) -> list[str]:
    return sorted({item.evidence_id for item in evidence if predicate(item)})


def build_canonical_profile(evidence: list[EvidenceRecord]) -> dict[str, Any]:
    profile = {
        "candidate_overview": {
            "candidate_id": "candidate_arthur_vargas",
            "professional_identity": "Software engineer with evidence across backend/data-pipeline development, regulated bioinformatics systems, technical support, and documentation-heavy work.",
            "likely_seniority_band": {
                "value": "mid_to_senior",
                "basis": "Multiple resume and cover-letter variants describe 6+ years of experience and a Senior Software Engineer title at IQVIA.",
                "supporting_evidence_ids": ids_for_evidence(
                    evidence,
                    lambda e: "6+ years" in e.text.lower() or "senior software engineer" in e.text.lower(),
                ),
            },
            "recurring_strengths": [
                "Python-based backend and data-pipeline engineering",
                "Bioinformatics and healthcare-domain software in regulated settings",
                "CI/CD, containerization, and AWS deployment workflows",
                "Technical documentation and cross-functional communication",
                "User support, onboarding, and troubleshooting for internal teams",
            ],
            "strongest_adjacent_role_families": [
                "technical_support",
                "technical_writing",
                "solutions_engineering",
                "developer_support_or_developer_relations",
            ],
            "supporting_evidence_ids": ids_for_evidence(
                evidence,
                lambda e: any(tag in e.role_tags for tag in ["software_engineering", "technical_support", "technical_writing"]),
            ),
        },
        "target_role_families": [
            {
                "role_family": "software_engineering",
                "support_level": "strong",
                "why_supported": "Repeated evidence across multiple resumes and cover letters shows backend services, REST APIs, data pipelines, cloud deployments, and production CI/CD ownership.",
                "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "software_engineering" in e.role_tags),
            },
            {
                "role_family": "technical_support",
                "support_level": "moderate",
                "why_supported": "The archive includes direct support claims plus examples of onboarding users, troubleshooting data-pipeline tooling, and serving as a primary technical contact.",
                "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "technical_support" in e.role_tags),
            },
            {
                "role_family": "technical_writing",
                "support_level": "moderate",
                "why_supported": "Multiple sources mention user guides, SOPs, architecture specs, release notes, and the ability to explain complex topics to technical and non-technical audiences.",
                "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "technical_writing" in e.role_tags),
            },
            {
                "role_family": "solutions_engineering",
                "support_level": "emerging",
                "why_supported": "Cross-functional translation work, stakeholder collaboration, and user-guidance examples suggest transferability into solutions or implementation-oriented roles.",
                "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "solutions_engineering" in e.role_tags),
            },
            {
                "role_family": "customer_success",
                "support_level": "emerging",
                "why_supported": "There is some evidence of end-user guidance, onboarding, and support communication, but most source material is still centered on engineering roles.",
                "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "customer_success" in e.role_tags),
            },
        ],
        "experience_history": [
            {
                "experience_id": "exp_iqvia_senior_software_engineer",
                "employer": "IQVIA",
                "role_title": "Senior Software Engineer",
                "date_range": "NOV 2021 – SEP 2024",
                "responsibilities": [
                    "Led development of high-throughput and primary-analysis data pipelines in Python/Bash/Groovy.",
                    "Built Python CLI tools, Flask APIs, ETL workflows, and QC reporting systems integrating LIMS and sequencer data.",
                    "Containerized multi-service workloads and deployed them on AWS ECS with CI/CD in AWS and Azure DevOps.",
                    "Supported users through onboarding, troubleshooting, documentation, and primary technical-contact responsibilities.",
                ],
                "tools_used": ["Python", "Bash", "Groovy", "Nextflow", "Docker", "AWS ECS", "Azure DevOps", "Flask", "MySQL", "Elasticsearch", "Redis"],
                "outcomes": [
                    "Enabled faster QC reporting and data delivery.",
                    "Improved Docker build times and release traceability.",
                    "Coordinated a global team of 3–4 engineers.",
                ],
                "supporting_evidence_ids": ids_for_evidence(
                    evidence,
                    lambda e: e.organization_or_project == "IQVIA" and ("global team" in e.text.lower() or "qc reports" in e.text.lower() or "support materials" in e.text.lower() or "aws ecs" in e.text.lower()),
                ),
            },
            {
                "experience_id": "exp_iqvia_software_engineer_iii",
                "employer": "IQVIA",
                "role_title": "Software Engineer III",
                "date_range": "NOV 2019 – NOV 2021",
                "responsibilities": [
                    "Partnered with product managers, SMEs, and IT architects to scope technical stories into two-week Agile sprints.",
                    "Standardized build/deploy automation using reusable Azure DevOps YAML pipeline templates.",
                ],
                "tools_used": ["Azure DevOps", "YAML", "Agile/Scrum"],
                "outcomes": ["Improved consistency across services through reusable automation templates."],
                "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "azure devops yaml pipeline templates" in e.text.lower() or "technical stories" in e.text.lower()),
            },
            {
                "experience_id": "exp_iqvia_software_engineer_ii",
                "employer": "IQVIA",
                "role_title": "Software Engineer II",
                "date_range": "OCT 2018 – NOV 2019",
                "responsibilities": [
                    "Developed Python tools for large dataset migration to AWS S3 and compute workflows on AWS."
                ],
                "tools_used": ["Python", "AWS S3"],
                "outcomes": ["Supported data migration and AWS compute workflows."],
                "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "large dataset migration" in e.text.lower()),
            },
        ],
        "projects": [
            {
                "project_id": "proj_gene_annotator",
                "project_name": "Gene Annotator",
                "project_type": "Personal/portfolio web application",
                "problem_context": "Genomic data processing and microblogging application used to demonstrate full-stack and data-pipeline capabilities.",
                "actions_taken": [
                    "Built a Python ETL pipeline using Pandas and SQLAlchemy.",
                    "Developed a Flask web app and REST API.",
                    "Added Elasticsearch search and Redis Queue background notifications.",
                    "Deployed Dockerized microservices to AWS ECS with CI/CD.",
                ],
                "tools_skills_involved": ["Python", "Pandas", "SQLAlchemy", "Flask", "Elasticsearch", "Redis", "Docker", "AWS ECS", "CI/CD"],
                "outputs_or_outcomes": ["Portfolio-quality demonstration of backend, data, search, and deployment skills."],
                "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: e.organization_or_project == "Gene Annotator"),
            },
            {
                "project_id": "proj_qc_reporting_cli",
                "project_name": "LIMS + Genexus QC Reporting CLI",
                "project_type": "Internal engineering tool",
                "problem_context": "Needed to combine laboratory and project-management data into faster operational QC reporting.",
                "actions_taken": [
                    "Extracted XML-based project data from an internal LIMS database.",
                    "Merged it with JSON data from sequencer REST APIs.",
                    "Generated comprehensive QC reports for users previously doing manual CLI/file work.",
                ],
                "tools_skills_involved": ["Python", "CLI tooling", "XML", "JSON", "REST APIs", "LIMS", "MySQL/SQLite"],
                "outputs_or_outcomes": ["Faster QC activities, operational reporting, and client data delivery."],
                "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "genexus" in e.text.lower() or "qc reports" in e.text.lower()),
            },
            {
                "project_id": "proj_samplesheet_parser",
                "project_name": "Sequencing Samplesheet Parser Module",
                "project_type": "Internal pipeline component",
                "problem_context": "Needed to split run-level sequencing samplesheets into client/project-specific inputs for downstream demultiplexing and delivery.",
                "actions_taken": [
                    "Built a family of Python parser classes with shared validation logic.",
                    "Used inheritance to handle instrument-specific behaviors.",
                    "Supported data organization standards across local HPC and AWS EC2 environments.",
                ],
                "tools_skills_involved": ["Python", "Object-oriented design", "Validation", "HPC", "AWS EC2", "Bioinformatics pipelines"],
                "outputs_or_outcomes": ["Reusable module later adopted by other pipelines and extensible to new instruments."],
                "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "samplesheet" in e.text.lower() or "clientid" in e.text.lower()),
            },
        ],
        "skills": {
            "programming_and_scripting": [
                skill_entry("Python", "strong", evidence, ["python"]),
                skill_entry("Bash", "medium", evidence, ["bash"]),
                skill_entry("Java/Groovy", "medium", evidence, ["java"]),
                skill_entry("JavaScript/React", "weak", evidence, ["javascript"]),
            ],
            "systems_and_infrastructure": [
                skill_entry("AWS", "strong", evidence, ["aws"]),
                skill_entry("Docker", "strong", evidence, ["docker"]),
                skill_entry("CI/CD automation", "strong", evidence, ["ci_cd"]),
                skill_entry("Nextflow", "strong", evidence, ["nextflow"]),
            ],
            "documentation_and_writing": [
                skill_entry("Technical documentation", "strong", evidence, ["technical_documentation"]),
            ],
            "troubleshooting_and_support": [
                skill_entry("Troubleshooting and technical support", "medium", evidence, ["troubleshooting"]),
            ],
            "customer_communication": [
                skill_entry("Cross-functional and user-facing communication", "medium", evidence, ["technical_documentation", "troubleshooting"]),
            ],
            "collaboration_and_process": [
                skill_entry("Technical leadership", "medium", evidence, ["leadership"]),
                skill_entry("Testing and quality practices", "medium", evidence, ["testing"]),
            ],
        },
        "tools_and_technologies": [
            tool_entry("tool_python", "Python", evidence, ["python"]),
            tool_entry("tool_flask", "Flask", evidence, ["flask"]),
            tool_entry("tool_sqlalchemy", "SQLAlchemy", evidence, ["sqlalchemy"]),
            tool_entry("tool_mysql_sqlite_postgres", "MySQL / SQLite / PostgreSQL (upskilling)", evidence, ["sql"]),
            tool_entry("tool_aws", "AWS (EC2, ECS, ECR, S3, IAM, CodePipeline/CodeBuild, Lambda)", evidence, ["aws"]),
            tool_entry("tool_docker", "Docker", evidence, ["docker"]),
            tool_entry("tool_nextflow", "Nextflow", evidence, ["nextflow"]),
            tool_entry("tool_elasticsearch", "Elasticsearch / Kibana", evidence, ["elasticsearch"]),
            tool_entry("tool_redis", "Redis Queue", evidence, ["redis"]),
            tool_entry("tool_pytest", "Pytest / BATS / coverage", evidence, ["testing"]),
            tool_entry("tool_rag_llms", "RAG pipelines / vector databases / multi-agent orchestration", evidence, ["rag_and_llms"]),
        ],
        "domains": [
            domain_entry("domain_genomics", "Genomics / bioinformatics", evidence, "genomics"),
            domain_entry("domain_healthcare", "Healthcare / oncology / clinical systems", evidence, "healthcare"),
            domain_entry("domain_internal_tools", "Internal research and operational tooling", evidence, "saas_internal_tools"),
            domain_entry("domain_ai_ml", "AI / LLM workflow learning", evidence, "ai_ml"),
        ],
        "writing_and_communication": {
            "summary": "Evidence supports clear technical writing, user guidance, architecture documentation, and communication with both technical and non-technical audiences.",
            "examples": [
                "Wrote design docs, architecture specs, user guides, release notes, manuals, SOPs, and troubleshooting guides.",
                "Explained complex topics to technical and non-technical audiences.",
                "Application responses and cover letters show coherent, reflective long-form writing.",
            ],
            "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "technical_writing" in e.role_tags or e.evidence_type == "writing_sample"),
        },
        "customer_support_and_success": {
            "summary": "The archive shows internal customer/support work rather than traditional external customer-success ownership.",
            "examples": [
                "Served as primary technical contact for internal scientific teams, project management, and business analysts.",
                "Guided users through onboarding, usage, and troubleshooting of data-pipeline tools.",
                "Resume variants explicitly frame technical support and incident-management skills.",
            ],
            "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "technical_support" in e.role_tags or e.evidence_type == "customer_interaction"),
        },
        "leadership_and_collaboration": {
            "summary": "Evidence supports tech-lead behavior, sprint planning, code reviews, and cross-functional collaboration with scientists, PMs, IT architects, QA, and regulatory stakeholders.",
            "examples": [
                "Coordinated a global team of 3–4 engineers.",
                "Partnered with product managers, SMEs, IT architects, bioinformaticians, QA teams, and regulatory stakeholders.",
                "Translated end-user needs into technical stories for sprint delivery.",
            ],
            "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: e.evidence_type == "leadership" or "solutions_engineering" in e.role_tags),
        },
        "achievements": [
            {
                "achievement_id": "ach_qc_reporting_automation",
                "summary": "Built QC reporting automation that reduced manual searching and sped up data delivery.",
                "metric_or_outcome": "Decreased time to deliver client data; enabled faster operational reporting and QC activities.",
                "context": "IQVIA clinical/bioinformatics tooling",
                "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "decreased the time" in e.text.lower() or "faster operational reporting" in e.text.lower() or "faster qc" in e.text.lower()),
            },
            {
                "achievement_id": "ach_container_release_reliability",
                "summary": "Improved Docker build times and release traceability through better image tagging and Dockerfile optimization.",
                "metric_or_outcome": "Decreased build times; improved immutability/traceability.",
                "context": "IQVIA CI/CD and deployment workflows",
                "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "decreased docker build times" in e.text.lower() or "traceability" in e.text.lower()),
            },
            {
                "achievement_id": "ach_samplesheet_reuse",
                "summary": "Created a reusable samplesheet parser architecture adopted by other pipelines.",
                "metric_or_outcome": "Reused by other pipelines; easier extension for new instruments.",
                "context": "Bioinformatics pipeline modernization",
                "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "reused by other pipelines" in e.text.lower() or "new instruments" in e.text.lower()),
            },
        ],
        "education_and_credentials": {
            "education": [
                {
                    "credential_id": "edu_bs_biology_ncsu",
                    "credential": "B.S. Biology",
                    "institution": "North Carolina State University",
                    "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "b.s. biology" in e.text.lower()),
                },
                {
                    "credential_id": "edu_ba_english_ncsu",
                    "credential": "B.A. English",
                    "institution": "North Carolina State University",
                    "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "b.a. english" in e.text.lower()),
                    "status": "needs_confirmation",
                },
            ],
            "professional_development": [
                {
                    "credential_id": "cred_parsity_ai_accelerator",
                    "credential": "Parsity AI Accelerator Program",
                    "status": "in_progress",
                    "expected_completion": "2026 (month varies by source)",
                    "focus_areas": ["RAG pipelines", "vector databases", "multi-agent orchestration", "LLM foundations", "retrieval optimization"],
                    "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "parsity" in e.text.lower() or "rag pipelines" in e.text.lower()),
                }
            ],
        },
        "preferences_and_motivators": [
            {
                "preference_id": "pref_meaningful_impact",
                "summary": "Prefers roles with meaningful social or healthcare impact.",
                "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "meaningful impact" in e.text.lower() or "improves the lives of patients" in e.text.lower() or "social impact" in e.text.lower()),
                "status": "stated_preference",
            },
            {
                "preference_id": "pref_growth_in_ai",
                "summary": "Actively seeking opportunities to grow in AI/LLM technologies while leveraging existing backend/data skills.",
                "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "rag" in e.text.lower() or "new technologies" in e.text.lower() or "technical growth" in e.text.lower()),
                "status": "stated_preference",
            },
            {
                "preference_id": "pref_customer_facing_technical_work",
                "summary": "Some materials suggest interest in customer-facing technical work, support, and user guidance.",
                "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: "guided users" in e.text.lower() or "technical support" in e.text.lower() or "technical contact" in e.text.lower()),
                "status": "inferred_from_materials",
            },
        ],
        "constraints_or_unknowns": [
            {
                "issue_id": "unknown_email_variants",
                "summary": "Email address differs across source documents.",
                "details": "Most files use arthurvargasdev@gmail.com, but one cover letter uses ahvargas92@gmail.com.",
            },
            {
                "issue_id": "unknown_ai_program_completion_month",
                "summary": "Expected completion date for Parsity AI Accelerator differs by source.",
                "details": "Most resume variants say May 2026, while one cover letter says April 2026.",
            },
            {
                "issue_id": "unknown_education_dual_degree",
                "summary": "Only one resume mentions a B.A. English in addition to the B.S. Biology.",
                "details": "Needs confirmation before treating the English degree as canonical.",
            },
            {
                "issue_id": "unknown_support_scope",
                "summary": "Support experience is clearly evidenced for internal teams, but direct external customer support scope is less explicit.",
                "details": "Important for tailoring into customer-success or support-specific applications.",
            },
        ],
    }
    validate_canonical_profile(profile)
    return profile


def skill_entry(skill_name: str, evidence_strength: str, evidence: list[EvidenceRecord], skill_tags: list[str]) -> dict[str, Any]:
    return {
        "skill_name": skill_name,
        "evidence_strength": evidence_strength,
        "contexts": sorted(
            {
                (item.organization_or_project or item.source_file)
                for item in evidence
                if any(tag in item.skill_tags for tag in skill_tags)
            }
        ),
        "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: any(tag in e.skill_tags for tag in skill_tags)),
    }


def tool_entry(tool_id: str, name: str, evidence: list[EvidenceRecord], skill_tags: list[str]) -> dict[str, Any]:
    return {
        "tool_id": tool_id,
        "name": name,
        "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: any(tag in e.skill_tags for tag in skill_tags)),
    }


def domain_entry(domain_id: str, name: str, evidence: list[EvidenceRecord], tag: str) -> dict[str, Any]:
    return {
        "domain_id": domain_id,
        "name": name,
        "supporting_evidence_ids": ids_for_evidence(evidence, lambda e: tag in e.domain_tags),
    }


def build_open_questions() -> str:
    return """# Open Questions

1. Which email address should be treated as current and canonical?
Most documents use `arthurvargasdev@gmail.com`, but `vargas_software_engineer_cover_letter (1).docx` uses `ahvargas92@gmail.com`.

2. What is the correct expected completion date for the Parsity AI Accelerator Program?
Most resumes say `May 2026`, while `vargas_software_engineer_cover_letter.docx` says `April 2026`.

3. Is the B.A. English an earned degree that should always be included?
`vargas_technical_support_engineer_resume.docx` lists both `B.S. Biology` and `B.A. English`, while the other resume versions only show Biology.

4. How much direct external customer support experience should be claimed?
The archive clearly supports internal user support, onboarding, troubleshooting, and technical-contact work, but the boundary between internal support and external customer-facing support should be clarified for support-focused applications.
"""


def build_profile_summary(profile: dict[str, Any], evidence: list[EvidenceRecord]) -> str:
    strong_evidence = [e for e in evidence if e.strength == "strong"]
    return f"""# Candidate Profile Summary

## Snapshot

Arthur Vargas is best supported for backend/data-pipeline software engineering work with strong adjacent evidence for technical support, technical writing, and cross-functional technical communication. The archive consistently describes 6+ years of engineering experience, including a Senior Software Engineer role at IQVIA focused on genomics-oriented clinical and research tooling.

## Strongest Role Families

- Software engineering: repeated evidence across resume and cover-letter variants for Python services, ETL, REST APIs, CLI tooling, cloud deployments, and CI/CD.
- Technical support: evidence of onboarding, troubleshooting, internal user guidance, and primary technical-contact responsibilities.
- Technical writing: repeated documentation, user-guide, SOP, architecture-specification, and troubleshooting-guide examples.
- Solutions/implementation-adjacent work: stakeholder translation, sprint scoping, and regulated cross-functional collaboration.

## Strongest Evidence Themes

- Bioinformatics and healthcare systems: genomic sequencing, oncology diagnostics, Nextflow pipelines, LIMS integration, and regulated/FDA-aware development.
- Python platform work: ETL pipelines, Flask APIs, CLI tools, data modeling, and automation workflows.
- Cloud and release engineering: Docker, AWS ECS/ECR/S3, CI/CD in AWS and Azure DevOps, immutable tagging, and deployment traceability.
- Writing and communication: Confluence docs, user guides, manuals, troubleshooting guides, and application materials that explain technical context clearly.
- Support and empathy: internal user support, onboarding, and tooling designed to reduce manual work and speed delivery.

## Notable Projects and Proof Points

- Gene Annotator: portfolio project showing ETL, API, search, background jobs, Dockerized microservices, AWS ECS deployment, and CI/CD.
- LIMS + Genexus QC Reporting CLI: evidence of automating manual operational workflows and improving delivery speed.
- Samplesheet parser module: good proof of maintainable object-oriented design and reuse within sequencing pipelines.

## Evidence Bank Notes

- Total evidence records: {len(evidence)}
- Strong evidence records: {len(strong_evidence)}
- Document types covered: {", ".join(sorted({doc_type_label(e.doc_type) for e in evidence}))}

## Main Cautions

- Contact and credential details have a few contradictions that should be resolved before downstream drafting.
- Technical-support evidence is meaningful, but much of it is internal-user support rather than clearly external customer support.
- AI/LLM work is recent and promising, but currently belongs in the emerging/upskilling bucket rather than as deeply proven production experience.
"""


def doc_type_label(doc_type: str) -> str:
    return {
        "resume": "resume",
        "cover_letter": "cover letter",
        "application_qa": "application Q/A",
        "other": "other material",
    }.get(doc_type, doc_type)


def build_style_samples(docs: list[ParsedDoc]) -> list[dict[str, Any]]:
    samples = []
    idx = 1
    for doc in docs:
        if doc.doc_type != "cover_letter":
            continue
        for para in doc.paragraphs:
            text = para.text
            text = re.sub(r"^\([^)]*\)", "", text).strip()
            lower = text.lower()
            if (
                len(text) < 120
                or is_contact_line(text)
                or "your resume" in lower
                or "resume honest" in lower
                or "for this posting" in lower
            ):
                continue
            samples.append(
                {
                    "sample_id": f"style_{idx:03d}",
                    "source_file": doc.source_file,
                    "doc_type": doc.doc_type,
                    "source_location": f"paragraph_{para.index}",
                    "text": text,
                    "style_notes": infer_style_notes(text),
                }
            )
            idx += 1
    return samples


def infer_style_notes(text: str) -> list[str]:
    notes = []
    lower = text.lower()
    if "i am interested" in lower or "i’m interested" in lower or "i'm interested" in lower:
        notes.append("direct_statement_of_interest")
    if "for example" in lower:
        notes.append("concrete_example_included")
    if any(k in lower for k in ["meaningful", "impact", "patient", "healthcare", "equitable"]):
        notes.append("mission_or_values_oriented")
    if any(k in lower for k in ["collaborated", "partnered", "worked closely"]):
        notes.append("collaborative_tone")
    return notes


def validate_outputs(canonical_profile: dict[str, Any], evidence: list[EvidenceRecord]) -> None:
    ids = [item.evidence_id for item in evidence]
    if len(ids) != len(set(ids)):
        raise SystemExit("Duplicate evidence IDs detected.")
    json.dumps(canonical_profile)
    for item in evidence:
        json.dumps(item.as_json())


def validate_canonical_profile(profile: dict[str, Any]) -> None:
    overview_ids = profile["candidate_overview"]["likely_seniority_band"]["supporting_evidence_ids"]
    if not overview_ids:
        raise SystemExit("Missing supporting evidence for candidate overview seniority.")
    for role in profile["target_role_families"]:
        if not role["supporting_evidence_ids"]:
            raise SystemExit(f"Missing supporting evidence for role family {role['role_family']}.")
    for exp in profile["experience_history"]:
        if not exp["supporting_evidence_ids"]:
            raise SystemExit(f"Missing supporting evidence for experience {exp['experience_id']}.")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")


def main() -> None:
    docs = collect_docs()
    evidence = build_evidence_bank(docs)
    canonical_profile = build_canonical_profile(evidence)
    style_samples = build_style_samples(docs)
    validate_outputs(canonical_profile, evidence)

    DERIVED_DIR.mkdir(exist_ok=True)
    write_json(DERIVED_DIR / "canonical_profile.json", canonical_profile)
    write_jsonl(DERIVED_DIR / "evidence_bank.jsonl", [item.as_json() for item in evidence])
    write_jsonl(DERIVED_DIR / "style_samples.jsonl", style_samples)
    (DERIVED_DIR / "profile_summary.md").write_text(build_profile_summary(canonical_profile, evidence), encoding="utf-8")
    (DERIVED_DIR / "open_questions.md").write_text(build_open_questions(), encoding="utf-8")
    write_json(
        DERIVED_DIR / "source_documents.json",
        {
            "source_count": len(docs),
            "sources": [
                {
                    "source_file": doc.source_file,
                    "doc_type": doc.doc_type,
                    "paragraph_count": len(doc.paragraphs),
                }
                for doc in docs
            ],
        },
    )


if __name__ == "__main__":
    main()
