from __future__ import annotations

from typing import Any

from .models import CompanyAssessment
from .reporting import format_matched_job_urls, format_matched_jobs, format_results


def print_run_results(
    *,
    skipped_assessments: list[CompanyAssessment],
    final_assessments: list[CompanyAssessment],
    refreshed_jobs: list[Any],
) -> None:
    assessments = skipped_assessments + final_assessments
    output = format_results(assessments)
    matched_jobs_section = format_matched_jobs(refreshed_jobs)
    matched_urls_section = format_matched_job_urls(refreshed_jobs)
    print(output + matched_jobs_section + matched_urls_section)