from __future__ import annotations

from .common import company_cache_key, log_step
from .registry_service import sync_company_registry
from .snapshot import (
    load_matched_jobs_snapshot,
    merge_matched_jobs_snapshot,
    save_matched_jobs,
)
from .workflow import build_search_record, sync_non_greenhouse_company_revisits


def persist_crawl_results(
    *,
    app,
    runtime_state,
    targets: list,
    final_assessments: list,
    refreshed_jobs: list,
    today_iso: str,
    search_cache: dict[str, dict],
    non_greenhouse_cache: dict[str, str],
    greenhouse_assessments_by_key: dict,
    crawl_run,
    phenom_run,
    workday_run,
    registry_service_context,
) -> None:
    refreshed_company_keys = {company_cache_key(company.name) for company in targets}
    merged_jobs = merge_matched_jobs_snapshot(
        load_matched_jobs_snapshot(app.matched_jobs_path),
        refreshed_jobs,
        refreshed_company_keys,
    )
    written = save_matched_jobs(app.matched_jobs_path, merged_jobs)
    log_step(f"Wrote {written} matched jobs to {app.matched_jobs_path}")

    for assessment in final_assessments:
        search_cache[company_cache_key(assessment.name)] = build_search_record(
            assessment, today_iso=today_iso
        )
        greenhouse_assessment = greenhouse_assessments_by_key.get(
            company_cache_key(assessment.name)
        )
        if (
            greenhouse_assessment is not None
            and greenhouse_assessment.status == "Greenhouse board not found"
        ):
            non_greenhouse_cache[company_cache_key(greenhouse_assessment.name)] = (
                greenhouse_assessment.name
            )
        else:
            non_greenhouse_cache.pop(company_cache_key(assessment.name), None)

    written_search_records = runtime_state.save_company_search_cache(search_cache)
    written_non_greenhouse = runtime_state.save_non_greenhouse_companies(non_greenhouse_cache)
    synced_company_revisits = sync_non_greenhouse_company_revisits(
        load_company_revisit_records=runtime_state.load_company_revisit_records,
        save_company_revisit_records=runtime_state.save_company_revisit_records,
        load_company_search_cache=runtime_state.load_company_search_cache,
        load_non_greenhouse_companies=runtime_state.load_non_greenhouse_companies,
        default_non_greenhouse_revisit_days=app.default_non_greenhouse_revisit_days,
        search_cache=search_cache,
        non_greenhouse_cache=non_greenhouse_cache,
        today_iso=today_iso,
    )
    log_step(
        f"Updated {written_search_records} search-cache records in {app.searched_companies_path}"
    )
    log_step(
        f"Recorded {written_non_greenhouse} non-Greenhouse companies in {app.non_greenhouse_companies_path}"
    )
    log_step(
        f"Tracked {synced_company_revisits} new ATS research follow-ups in {app.company_revisit_path}"
    )
    written_registry_records = sync_company_registry(
        registry_service_context,
        search_cache=search_cache,
        non_greenhouse_cache=non_greenhouse_cache,
        company_revisits=runtime_state.load_company_revisit_records(),
        greenhouse_assessments=crawl_run.assessments,
        workday_assessments=workday_run.assessments if workday_run is not None else (),
        other_ats_assessments=phenom_run.assessments if phenom_run is not None else (),
    )
    log_step(
        f"Updated {written_registry_records} company ATS registry records in {app.company_registry_path}"
    )