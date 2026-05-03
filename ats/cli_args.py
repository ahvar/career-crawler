from __future__ import annotations

import argparse

from .common import clean_display_text
from .workflow import parse_iso_date


def parse_args(
    *,
    default_target_company_count: int,
    default_delay_seconds: float,
    default_concurrency: int,
    default_timeout_seconds: int,
    default_workday_discovery_limit: int,
    valid_job_tracking_statuses: tuple[str, ...],
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ATS-aware job crawler for target companies.")
    parser.add_argument(
        "--company",
        action="append",
        default=[],
        help="Limit the run to one or more company names. Repeat the flag to provide multiple names.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=default_target_company_count,
        help=f"Maximum number of companies to process. Default: {default_target_company_count}.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=default_delay_seconds,
        help=f"Minimum delay in seconds between API requests. Default: {default_delay_seconds}.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=default_concurrency,
        help=f"Maximum in-flight API requests. Default: {default_concurrency}.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=default_timeout_seconds,
        help=f"Per-request timeout in seconds. Default: {default_timeout_seconds}.",
    )
    parser.add_argument(
        "--show-cache-stats",
        action="store_true",
        help="Print matched-job output and archive counts, then exit.",
    )
    parser.add_argument(
        "--show-company-list",
        action="store_true",
        help="Print the default target company list and exit.",
    )
    parser.add_argument(
        "--show-tracking-report",
        action="store_true",
        help="Print a report that joins matched jobs with job/company tracking overlays, then exit.",
    )
    parser.add_argument(
        "--show-company-ats-report",
        action="store_true",
        help="Print a report summarizing which companies are confirmed Greenhouse, confirmed Workday, or queued for Workday research.",
    )
    parser.add_argument(
        "--show-intake-workday-report",
        action="store_true",
        help="Print a focused ATS report for companies listed in new_companies.txt.",
    )
    parser.add_argument(
        "--set-company-workday-board",
        action="store_true",
        help="Record a validated Workday board in workday_board_hints.json and the company ATS registry.",
    )
    parser.add_argument(
        "--discover-workday-boards",
        action="store_true",
        help="Probe the current Workday discovery queue for valid Workday board patterns.",
    )
    parser.add_argument(
        "--apply-discovered-workday-boards",
        action="store_true",
        help="Persist confirmed Workday discovery results instead of running in dry-run mode.",
    )
    parser.add_argument(
        "--apply-workday-not-found-results",
        action="store_true",
        help="Persist clean Workday not_found discovery results so Greenhouse-not-found companies advance into check_other_ats.",
    )
    parser.add_argument(
        "--workday-discovery-limit",
        type=int,
        default=default_workday_discovery_limit,
        help=f"Maximum number of queued companies to probe for Workday boards. Default: {default_workday_discovery_limit}.",
    )
    parser.add_argument(
        "--company-name",
        help="Canonical company name used with --set-company-workday-board.",
    )
    parser.add_argument(
        "--workday-tenant",
        help="Workday tenant used with --set-company-workday-board.",
    )
    parser.add_argument(
        "--workday-site-id",
        help="Workday site id used with --set-company-workday-board.",
    )
    parser.add_argument(
        "--workday-board-url",
        help="Workday board URL used with --set-company-workday-board.",
    )
    parser.add_argument(
        "--sync-non-greenhouse-revisits",
        action="store_true",
        help="Backfill non-Greenhouse companies into crawler_cache/company_revisit.jsonl as ATS research follow-ups.",
    )
    parser.add_argument(
        "--set-job-status",
        choices=valid_job_tracking_statuses,
        help="Upsert a job-level tracking record in crawler_cache/job_tracking.jsonl.",
    )
    parser.add_argument(
        "--backfill-pending-review",
        action="store_true",
        help="Create pending_review tracking records for matched jobs that exist in the current snapshot but are missing from crawler_cache/job_tracking.jsonl.",
    )
    parser.add_argument(
        "--backfill-workday-snapshot-details",
        action="store_true",
        help="Refresh existing Workday matched-job snapshot rows with live descriptions and canonical job URLs. Use --company to scope to specific companies.",
    )
    parser.add_argument(
        "--company-slug",
        help="Company slug for a job tracking update, for example 'affirm' or 'instacart'.",
    )
    parser.add_argument(
        "--job-id",
        help="Job id for a job tracking update. Supports existing Greenhouse numeric ids and Workday ids.",
    )
    parser.add_argument(
        "--review-date",
        help="Review date to store on the job tracking record in ISO format (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--application-date",
        help="Application date to store on the job tracking record in ISO format (YYYY-MM-DD). Use an empty string to clear it.",
    )
    parser.add_argument(
        "--next-action-date",
        help="Next action date to store on the job tracking record in ISO format (YYYY-MM-DD). Use an empty string to clear it.",
    )
    parser.add_argument(
        "--notes",
        help="Freeform notes to store on the job tracking record.",
    )
    parser.add_argument(
        "--match-rationale",
        help="Short rationale explaining why the job was marked with this status.",
    )
    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be at least 1.")
    if args.delay <= 0:
        parser.error("--delay must be greater than 0.")
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1.")
    if args.timeout < 1:
        parser.error("--timeout must be at least 1.")
    if args.workday_discovery_limit < 1:
        parser.error("--workday-discovery-limit must be at least 1.")
    if args.set_job_status and (not args.company_slug or not clean_display_text(str(args.job_id or ""))):
        parser.error("--set-job-status requires both --company-slug and --job-id.")
    if args.set_company_workday_board and not all(
        (
            clean_display_text(str(args.company_name or "")),
            clean_display_text(str(args.workday_tenant or "")),
            clean_display_text(str(args.workday_site_id or "")),
            clean_display_text(str(args.workday_board_url or "")),
        )
    ):
        parser.error("--set-company-workday-board requires --company-name, --workday-tenant, --workday-site-id, and --workday-board-url.")
    if not args.set_job_status and not args.set_company_workday_board and not args.backfill_pending_review and any(
        value is not None
        for value in (args.company_slug, args.job_id, args.review_date, args.application_date, args.next_action_date, args.notes, args.match_rationale)
    ):
        parser.error("Job tracking update flags require --set-job-status or --backfill-pending-review.")
    if args.backfill_pending_review and any(value is not None for value in (args.company_slug, args.job_id, args.application_date, args.next_action_date)):
        parser.error("--backfill-pending-review does not support --company-slug, --job-id, --application-date, or --next-action-date.")
    for value, flag_name in (
        (args.review_date, "--review-date"),
        (args.application_date, "--application-date"),
        (args.next_action_date, "--next-action-date"),
    ):
        if value not in (None, "") and parse_iso_date(value) is None:
            parser.error(f"{flag_name} must use YYYY-MM-DD format.")
    return args