from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from .common import clean_display_text, company_cache_key, dedupe_preserve_order, log_step, normalize_job_id
from .registry import (
    finalize_company_registry_record,
    get_workday_check_candidates,
    make_default_company_registry_record,
)
from .storage import atomic_write
from .workflow import build_non_greenhouse_revisit_record
from .workday_discovery import WorkdayBoardDiscoverer


@dataclass(frozen=True)
class CommandContext:
    matched_jobs_path: Path
    company_revisit_path: Path
    workday_board_hints_path: Path
    new_companies_path: Path
    default_company_names: tuple[str, ...]
    default_non_greenhouse_revisit_days: int
    valid_job_tracking_statuses: tuple[str, ...]
    workday_board_hints: dict[str, dict]
    crawl_error_type: type[Exception]
    summarize_output_stats: Callable[[], str]
    format_tracking_report: Callable[[], str]
    format_company_ats_report: Callable[[], str]
    format_intake_workday_report: Callable[[Path], str]
    format_workday_discovery_report: Callable[..., str]
    load_company_search_cache: Callable[[], dict[str, dict]]
    load_non_greenhouse_companies: Callable[[], dict[str, str]]
    load_company_revisit_records: Callable[[], dict[str, dict]]
    save_company_revisit_records: Callable[[dict[str, dict]], int]
    load_company_registry_records: Callable[[], dict[str, dict]]
    save_company_registry_records: Callable[[dict[str, dict]], int]
    load_job_tracking_records: Callable[[], dict[tuple[str, str], dict]]
    save_job_tracking_records: Callable[[dict[tuple[str, str], dict]], int]
    sync_company_registry: Callable[[], int]
    sync_non_greenhouse_company_revisits: Callable[..., int]
    upsert_job_tracking_record: Callable[..., dict]
    backfill_pending_review_records: Callable[..., int]
    backfill_workday_snapshot_details: Callable[..., int]


def should_exit_after_sync(args) -> bool:
    return args.sync_non_greenhouse_revisits and not any(
        (
            args.show_company_list,
            args.show_cache_stats,
            args.show_tracking_report,
            args.show_company_ats_report,
            args.show_intake_workday_report,
            args.set_company_workday_board,
            args.discover_workday_boards,
            args.set_job_status is not None,
            args.backfill_pending_review,
            args.backfill_workday_snapshot_details,
            args.company,
        )
    )


def load_workday_hint_payload(workday_board_hints_path: Path) -> dict[str, dict[str, str]]:
    if not workday_board_hints_path.exists():
        return {}
    try:
        payload = json.loads(workday_board_hints_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_workday_hint_payload(
    workday_board_hints_path: Path,
    payload: dict[str, dict[str, str]],
) -> None:
    atomic_write(workday_board_hints_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def record_missing_workday_board(context: CommandContext, company_name: str, detail: str) -> dict:
    normalized_company_name = clean_display_text(company_name)
    company_slug = company_cache_key(normalized_company_name)
    today = date.today()
    today_iso = today.isoformat()

    revisit_records = context.load_company_revisit_records()
    revisit_record = revisit_records.get(company_slug) or build_non_greenhouse_revisit_record(
        company_name=normalized_company_name,
        last_checked=today_iso,
        next_revisit=(today + timedelta(days=context.default_non_greenhouse_revisit_days)).isoformat(),
    )
    revisit_record = {
        **revisit_record,
        "company_name": normalized_company_name,
        "board_type": "ats_research",
        "last_checked": today_iso,
        "next_revisit": (today + timedelta(days=context.default_non_greenhouse_revisit_days)).isoformat(),
        "reason": "Greenhouse board not found; Workday board not found; investigate alternate ATS/job board.",
        "notes": detail,
    }
    revisit_records[company_slug] = revisit_record
    context.save_company_revisit_records(revisit_records)

    existing_records = context.load_company_registry_records()
    record = existing_records.get(company_slug) or make_default_company_registry_record(
        company_slug,
        normalized_company_name,
        context.workday_board_hints,
    )
    record.update(
        {
            "company_name": normalized_company_name,
            "workday_status": "not_found",
            "workday_status_detail": detail,
            "workday_last_checked": today_iso,
            "last_overall_check": today_iso,
        }
    )
    existing_records[company_slug] = finalize_company_registry_record(record, revisit_record)
    context.save_company_registry_records(existing_records)
    return existing_records[company_slug]


def promote_company_to_workday(
    context: CommandContext,
    *,
    company_name: str,
    tenant: str,
    site_id: str,
    board_url: str,
) -> dict:
    normalized_company_name = clean_display_text(company_name)
    if not normalized_company_name:
        raise context.crawl_error_type("Company name is required for Workday promotion.")

    normalized_tenant = clean_display_text(tenant)
    normalized_site_id = clean_display_text(site_id)
    normalized_board_url = clean_display_text(board_url)
    if not normalized_tenant or not normalized_site_id or not normalized_board_url:
        raise context.crawl_error_type("Workday promotion requires tenant, site id, and board URL.")

    payload = load_workday_hint_payload(context.workday_board_hints_path)
    payload[normalized_company_name] = {
        "tenant": normalized_tenant,
        "site_id": normalized_site_id,
        "board_url": normalized_board_url,
    }
    save_workday_hint_payload(context.workday_board_hints_path, payload)

    company_slug = company_cache_key(normalized_company_name)
    context.workday_board_hints[company_slug] = {
        "tenant": normalized_tenant,
        "site_id": normalized_site_id,
        "board_url": normalized_board_url,
    }

    revisit_records = context.load_company_revisit_records()
    today = date.today()
    today_iso = today.isoformat()
    revisit_record = revisit_records.get(company_slug)
    if revisit_record is None:
        revisit_record = {
            "company_slug": company_slug,
            "company_name": normalized_company_name,
            "board_type": "workday",
            "last_checked": today_iso,
            "next_revisit": (today + timedelta(days=context.default_non_greenhouse_revisit_days)).isoformat(),
            "reason": "Confirmed Workday board; refresh crawler for Austin/US-remote roles.",
            "notes": "Validated Workday board configuration.",
        }
    else:
        revisit_record = {
            **revisit_record,
            "company_name": normalized_company_name,
            "board_type": "workday",
            "last_checked": today_iso,
            "reason": "Confirmed Workday board; refresh crawler for Austin/US-remote roles.",
            "notes": clean_display_text(str(revisit_record.get("notes") or "")) or "Validated Workday board configuration.",
        }
    revisit_records[company_slug] = revisit_record
    context.save_company_revisit_records(revisit_records)

    existing_records = context.load_company_registry_records()
    record = existing_records.get(company_slug) or make_default_company_registry_record(
        company_slug,
        normalized_company_name,
        context.workday_board_hints,
    )
    record.update(
        {
            "company_name": normalized_company_name,
            "workday_status": "confirmed",
            "workday_board_url": normalized_board_url,
            "workday_tenant": normalized_tenant,
            "workday_site_id": normalized_site_id,
            "workday_last_checked": today_iso,
            "workday_status_detail": "Confirmed Workday board from manual validation.",
            "last_overall_check": today_iso,
        }
    )
    existing_records[company_slug] = finalize_company_registry_record(record, revisit_record)
    context.save_company_registry_records(existing_records)
    return existing_records[company_slug]


async def discover_workday_boards(
    context: CommandContext,
    *,
    company_names: list[str],
    limit: int,
    delay: float,
    concurrency: int,
    timeout: int,
    apply_confirmed_results: bool,
    apply_not_found_results: bool,
) -> list[dict]:
    records = context.load_company_registry_records()
    if company_names:
        record_names_by_key = {
            company_cache_key(record["company_name"]): record["company_name"]
            for record in records.values()
        }
        candidate_names = dedupe_preserve_order(
            record_names_by_key.get(company_cache_key(company_name), clean_display_text(company_name))
            for company_name in company_names
        )
    else:
        candidates = get_workday_check_candidates(records)
        candidate_names = [record["company_name"] for record in candidates]
    candidate_names = candidate_names[:limit]

    discoverer = WorkdayBoardDiscoverer(
        delay_seconds=delay,
        concurrency=concurrency,
        timeout_seconds=timeout,
    )
    results = await discoverer.discover_companies(candidate_names)

    if apply_confirmed_results or apply_not_found_results:
        for result in results:
            if apply_confirmed_results and result["status"] == "confirmed":
                promote_company_to_workday(
                    context,
                    company_name=result["company_name"],
                    tenant=result["tenant"],
                    site_id=result["site_id"],
                    board_url=result["board_url"],
                )
            elif apply_not_found_results and result["status"] == "not_found":
                record_missing_workday_board(context, result["company_name"], result["detail"])

    return results


async def handle_cli_command(args, context: CommandContext) -> int | None:
    if args.sync_non_greenhouse_revisits:
        created = context.sync_non_greenhouse_company_revisits(
            load_company_revisit_records=context.load_company_revisit_records,
            save_company_revisit_records=context.save_company_revisit_records,
            load_company_search_cache=context.load_company_search_cache,
            load_non_greenhouse_companies=context.load_non_greenhouse_companies,
            default_non_greenhouse_revisit_days=context.default_non_greenhouse_revisit_days,
        )
        log_step(f"Synced {created} non-Greenhouse company revisit records into {context.company_revisit_path}")

    if should_exit_after_sync(args):
        return 0

    if args.show_company_list:
        for company_name in context.default_company_names:
            print(company_name)
        return 0

    if args.show_cache_stats:
        print(context.summarize_output_stats())
        return 0

    if args.show_tracking_report:
        print(context.format_tracking_report())
        return 0

    if args.show_company_ats_report:
        context.sync_company_registry()
        print(context.format_company_ats_report())
        return 0

    if args.show_intake_workday_report:
        context.sync_company_registry()
        print(context.format_intake_workday_report(context.new_companies_path))
        return 0

    if args.set_company_workday_board:
        updated = promote_company_to_workday(
            context,
            company_name=clean_display_text(args.company_name or ""),
            tenant=clean_display_text(args.workday_tenant or ""),
            site_id=clean_display_text(args.workday_site_id or ""),
            board_url=clean_display_text(args.workday_board_url or ""),
        )
        print(json.dumps(updated, indent=2, sort_keys=True))
        return 0

    if args.discover_workday_boards:
        results = await discover_workday_boards(
            context,
            company_names=args.company,
            limit=args.workday_discovery_limit,
            delay=args.delay,
            concurrency=args.concurrency,
            timeout=args.timeout,
            apply_confirmed_results=args.apply_discovered_workday_boards,
            apply_not_found_results=args.apply_workday_not_found_results,
        )
        print(
            context.format_workday_discovery_report(
                results,
                applied=args.apply_discovered_workday_boards or args.apply_workday_not_found_results,
            )
        )
        return 0

    if args.set_job_status is not None:
        updated = context.upsert_job_tracking_record(
            company_slug=clean_display_text(args.company_slug or ""),
            greenhouse_job_id=normalize_job_id(args.job_id),
            status=args.set_job_status,
            review_date=args.review_date,
            application_date=args.application_date,
            next_action_date=args.next_action_date,
            notes=args.notes,
            match_rationale=args.match_rationale,
            valid_job_tracking_statuses=context.valid_job_tracking_statuses,
            crawl_error_type=context.crawl_error_type,
            load_job_tracking_records=context.load_job_tracking_records,
            save_job_tracking_records=context.save_job_tracking_records,
            matched_jobs_path=context.matched_jobs_path,
        )
        print(json.dumps(updated, indent=2, sort_keys=True))
        return 0

    if args.backfill_pending_review:
        created = context.backfill_pending_review_records(
            review_date=args.review_date,
            notes=args.notes,
            match_rationale=args.match_rationale,
            load_job_tracking_records=context.load_job_tracking_records,
            save_job_tracking_records=context.save_job_tracking_records,
            matched_jobs_path=context.matched_jobs_path,
        )
        print(f"Created {created} pending_review tracking records.")
        return 0

    if args.backfill_workday_snapshot_details:
        updated = context.backfill_workday_snapshot_details(
            company_names=args.company,
            timeout_seconds=args.timeout,
            matched_jobs_path=context.matched_jobs_path,
        )
        print(f"Updated {updated} Workday snapshot rows.")
        return 0

    return None