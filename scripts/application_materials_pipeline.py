#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from application_materials_content import generate_cover_letter_content, generate_resume_content
from candidate_evidence import (
    CandidateContext,
    load_candidate_context,
    select_relevant_evidence,
)
from config import Config
from application_materials_templates import (
    TemplateConfig,
    document_to_text,
    infer_generation_role_family,
    render_cover_letter_docx,
    render_resume_docx,
    template_config_for_role_family,
)
from job_details import JobDetails, fetch_job_details


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


def clean_display_text(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


def normalize_match_text(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[_/|]+", " ", lowered)
    lowered = re.sub(r"[^a-z0-9+&.-]+", " ", lowered)
    return " ".join(lowered.split())


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def make_client() -> OpenAI:
    if not Config.OPENAI_API_KEY:
        raise SystemExit("Missing OPENAI_API_KEY in environment or .env")
    if not Config.OPENAI_FINETUNED_MODEL:
        raise SystemExit("Missing OPENAI_FINETUNED_MODEL in environment or .env")
    return OpenAI(api_key=Config.OPENAI_API_KEY)


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