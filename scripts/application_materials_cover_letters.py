from __future__ import annotations

import re

from application_materials_templates import CoverLetterContent
from candidate_evidence import CandidateContext
from job_details import JobDetails


def clean_display_text(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


def normalize_match_text(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[_/|]+", " ", lowered)
    lowered = re.sub(r"[^a-z0-9+&.-]+", " ", lowered)
    return " ".join(lowered.split())


def join_phrases(items: list[str]) -> str:
    if not items:
        return "software engineering"
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def normalize_cover_letter_paragraphs(paragraphs: list[str]) -> list[str]:
    normalized: list[str] = []
    for paragraph in paragraphs:
        cleaned = clean_display_text(paragraph)
        if cleaned and cleaned[-1] not in ".!?":
            cleaned += "."
        normalized.append(cleaned)
    return normalized


def build_software_engineering_cover_letter(job: JobDetails, context: CandidateContext, infer_skill_labels) -> CoverLetterContent:
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


def generate_cover_letter_content(
    job: JobDetails,
    context: CandidateContext,
    role_family: str,
    infer_skill_labels,
) -> CoverLetterContent:
    if role_family == "software_engineering":
        return build_software_engineering_cover_letter(job, context, infer_skill_labels)
    if role_family == "technical_writing":
        return build_technical_writing_cover_letter(job, context)
    return build_customer_facing_cover_letter(job, context, role_family)