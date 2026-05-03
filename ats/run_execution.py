from __future__ import annotations

from dataclasses import dataclass

from .common import company_cache_key
from .models import CompanyAssessment, CrawlRun
from .phenompeople import has_phenom_search_hint
from .workday import has_workday_board_hint


@dataclass
class CrawlExecutionResult:
    crawl_run: CrawlRun
    phenom_run: CrawlRun | None
    workday_run: CrawlRun | None
    greenhouse_assessments_by_key: dict[str, CompanyAssessment]
    final_assessments: list[CompanyAssessment]
    refreshed_jobs: list


async def execute_crawl_passes(
    *,
    greenhouse_targets: list,
    workday_only_targets: list,
    run_greenhouse_pass,
    run_phenom_pass,
    run_workday_pass,
    args,
    targets: list,
) -> CrawlExecutionResult:
    crawl_run = await run_greenhouse_pass(args, greenhouse_targets=greenhouse_targets)
    greenhouse_assessments_by_key = {
        company_cache_key(assessment.name): assessment
        for assessment in crawl_run.assessments
    }
    phenom_run = await run_phenom_pass(
        args,
        greenhouse_targets=greenhouse_targets,
        crawl_run=crawl_run,
    )
    workday_run = await run_workday_pass(
        args,
        greenhouse_targets=greenhouse_targets,
        workday_only_targets=workday_only_targets,
        crawl_run=crawl_run,
        phenom_run=phenom_run,
    )
    replacement_assessments, replacement_jobs = merge_assessment_results(
        targets=targets,
        crawl_run=crawl_run,
        phenom_run=phenom_run,
        workday_run=workday_run,
    )
    final_assessments = [
        replacement_assessments[company_cache_key(target.name)] for target in targets
    ]
    refreshed_jobs = [
        job
        for target in targets
        for job in replacement_jobs[company_cache_key(target.name)]
    ]
    return CrawlExecutionResult(
        crawl_run=crawl_run,
        phenom_run=phenom_run,
        workday_run=workday_run,
        greenhouse_assessments_by_key=greenhouse_assessments_by_key,
        final_assessments=final_assessments,
        refreshed_jobs=refreshed_jobs,
    )


def merge_assessment_results(
    *,
    targets: list,
    crawl_run: CrawlRun,
    phenom_run,
    workday_run,
) -> tuple[dict[str, CompanyAssessment], dict[str, list]]:
    replacement_assessments = {
        company_cache_key(assessment.name): assessment
        for assessment in crawl_run.assessments
    }
    replacement_jobs: dict[str, list] = {
        company_cache_key(target.name): [] for target in targets
    }
    for assessment in crawl_run.assessments:
        replacement_jobs[company_cache_key(assessment.name)] = list(assessment.matched_jobs)

    for run in (phenom_run, workday_run):
        if run is None:
            continue
        for assessment in run.assessments:
            company_key = company_cache_key(assessment.name)
            replacement_assessments[company_key] = assessment
            replacement_jobs[company_key] = list(assessment.matched_jobs)

    return replacement_assessments, replacement_jobs


def build_phenom_targets(*, greenhouse_targets: list, crawl_run: CrawlRun) -> list:
    return [
        target
        for target, assessment in zip(greenhouse_targets, crawl_run.assessments)
        if has_phenom_search_hint(target.name) and assessment.status != "Matched jobs found"
    ]


def build_workday_targets(
    *,
    greenhouse_targets: list,
    workday_only_targets: list,
    crawl_run: CrawlRun,
    phenom_run,
) -> list:
    phenom_assessments_by_key = {
        company_cache_key(assessment.name): assessment
        for assessment in (phenom_run.assessments if phenom_run is not None else [])
    }
    return workday_only_targets + [
        target
        for target, assessment in zip(greenhouse_targets, crawl_run.assessments)
        if has_workday_board_hint(target.name)
        and phenom_assessments_by_key.get(
            company_cache_key(target.name), assessment
        ).status
        != "Matched jobs found"
    ]