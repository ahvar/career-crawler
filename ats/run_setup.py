from __future__ import annotations

import argparse

from .common import clean_display_text, company_cache_key
from .models import CompanyAssessment
from .registry_service import format_company_ats_report, format_intake_workday_report, sync_company_registry
from .reporting import (
    format_company_ats_report as render_company_ats_report,
    format_intake_workday_report as render_intake_workday_report,
    format_workday_discovery_report,
)
from .snapshot import backfill_workday_snapshot_details
from .tracking import format_tracking_report as render_tracking_report
from .tracking_service import format_tracking_report
from .workflow import (
    backfill_pending_review_records,
    build_cached_assessment,
    sync_non_greenhouse_company_revisits,
    upsert_job_tracking_record,
)


def build_command_context(app, *, crawl_error_type: type[Exception]):
    registry_service_context = app.make_registry_service_context(
        render_company_ats_report=render_company_ats_report,
        render_intake_workday_report=render_intake_workday_report,
    )
    tracking_service_context = app.make_tracking_service_context(
        render_tracking_report=render_tracking_report
    )
    command_context = app.make_command_context(
        crawl_error_type=crawl_error_type,
        format_tracking_report=lambda: format_tracking_report(tracking_service_context),
        format_company_ats_report=lambda: format_company_ats_report(registry_service_context),
        format_intake_workday_report=lambda path: format_intake_workday_report(
            registry_service_context, path
        ),
        format_workday_discovery_report=format_workday_discovery_report,
        sync_company_registry=lambda: sync_company_registry(registry_service_context),
        sync_non_greenhouse_company_revisits=sync_non_greenhouse_company_revisits,
        upsert_job_tracking_record=upsert_job_tracking_record,
        backfill_pending_review_records=backfill_pending_review_records,
        backfill_workday_snapshot_details=backfill_workday_snapshot_details,
    )
    return command_context, registry_service_context


def select_target_company_names(
    args: argparse.Namespace,
    *,
    app,
    search_cache: dict[str, dict],
    non_greenhouse_cache: dict[str, str],
) -> tuple[list[str], list[CompanyAssessment]]:
    skipped_assessments: list[CompanyAssessment] = []
    if args.company:
        return args.company[: args.limit], skipped_assessments

    selected_company_names: list[str] = []
    for company_name in app.default_target_companies:
        company_name = clean_display_text(company_name)
        if not company_name:
            continue
        company_key = company_cache_key(company_name)
        if company_key in non_greenhouse_cache:
            skipped_assessments.append(
                CompanyAssessment(
                    name=company_name,
                    attempted_slugs=[],
                    resolved_slug=None,
                    board_url=None,
                    status="Skipped (known non-Greenhouse)",
                )
            )
            continue
        cached_record = search_cache.get(company_key)
        if cached_record is not None:
            skipped_assessments.append(
                build_cached_assessment(
                    company_name=company_name,
                    record=cached_record,
                    status="Skipped (already searched)",
                )
            )
            continue
        selected_company_names.append(company_name)
        if len(selected_company_names) >= args.limit:
            break

    return selected_company_names, skipped_assessments


def partition_targets(targets: list, *, explicit_company_keys: set[str], has_workday_board_hint) -> tuple[list, list]:
    greenhouse_targets = [
        target
        for target in targets
        if not (
            company_cache_key(target.name) in explicit_company_keys
            and has_workday_board_hint(target.name)
        )
    ]
    workday_only_targets = [
        target
        for target in targets
        if company_cache_key(target.name) in explicit_company_keys
        and has_workday_board_hint(target.name)
    ]
    return greenhouse_targets, workday_only_targets