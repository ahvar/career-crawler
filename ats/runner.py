from __future__ import annotations

import argparse
from datetime import date

from .commands import handle_cli_command
from .common import company_cache_key
from .greenhouse import GreenhouseCrawler
from .intake import build_target_companies
from .models import CrawlRun
from .phenompeople import PhenomPeopleCrawler
from .run_execution import build_phenom_targets, build_workday_targets, execute_crawl_passes
from .run_output import print_run_results
from .run_persistence import persist_crawl_results
from .run_setup import build_command_context, partition_targets, select_target_company_names
from .workday import WorkdayCrawler, has_workday_board_hint


async def _run_greenhouse_pass(args: argparse.Namespace, *, greenhouse_targets: list) -> CrawlRun:
    if not greenhouse_targets:
        return CrawlRun(assessments=[], matched_jobs=[])

    crawler = GreenhouseCrawler(
        delay_seconds=args.delay,
        concurrency=args.concurrency,
        timeout_seconds=args.timeout,
    )
    return await crawler.crawl(greenhouse_targets)


async def _run_phenom_pass(
    args: argparse.Namespace,
    *,
    greenhouse_targets: list,
    crawl_run: CrawlRun,
):
    phenom_targets = build_phenom_targets(
        greenhouse_targets=greenhouse_targets,
        crawl_run=crawl_run,
    )
    if not phenom_targets:
        return None

    phenom_crawler = PhenomPeopleCrawler(
        delay_seconds=args.delay,
        concurrency=args.concurrency,
        timeout_seconds=args.timeout,
    )
    return await phenom_crawler.crawl(phenom_targets)


async def _run_workday_pass(
    args: argparse.Namespace,
    *,
    greenhouse_targets: list,
    workday_only_targets: list,
    crawl_run: CrawlRun,
    phenom_run,
):
    workday_targets = build_workday_targets(
        greenhouse_targets=greenhouse_targets,
        workday_only_targets=workday_only_targets,
        crawl_run=crawl_run,
        phenom_run=phenom_run,
    )
    if not workday_targets:
        return None

    workday_crawler = WorkdayCrawler(
        delay_seconds=args.delay,
        concurrency=args.concurrency,
        timeout_seconds=args.timeout,
    )
    return await workday_crawler.crawl(workday_targets)


async def run_crawl(args: argparse.Namespace, *, app, crawl_error_type: type[Exception]) -> int:
    runtime_state = app.runtime_state
    runtime_state.ensure_cache_dir()
    runtime_state.ensure_tracking_files()

    command_context, registry_service_context = build_command_context(
        app,
        crawl_error_type=crawl_error_type,
    )
    command_result = await handle_cli_command(args, command_context)
    if command_result is not None:
        return command_result

    search_cache = runtime_state.load_company_search_cache()
    non_greenhouse_cache = runtime_state.load_non_greenhouse_companies()
    selected_company_names, skipped_assessments = select_target_company_names(
        args,
        app=app,
        search_cache=search_cache,
        non_greenhouse_cache=non_greenhouse_cache,
    )

    targets = build_target_companies(
        selected_company_names,
        greenhouse_slug_hints=app.greenhouse_slug_hints,
    )
    if not targets and not skipped_assessments:
        raise crawl_error_type("No target companies were provided.")
    if not targets:
        print_run_results(
            skipped_assessments=skipped_assessments,
            final_assessments=[],
            refreshed_jobs=[],
        )
        return 0

    explicit_company_keys = {
        company_cache_key(company_name) for company_name in (args.company or [])
    }
    greenhouse_targets, workday_only_targets = partition_targets(
        targets,
        explicit_company_keys=explicit_company_keys,
        has_workday_board_hint=has_workday_board_hint,
    )
    execution = await execute_crawl_passes(
        greenhouse_targets=greenhouse_targets,
        workday_only_targets=workday_only_targets,
        run_greenhouse_pass=_run_greenhouse_pass,
        run_phenom_pass=_run_phenom_pass,
        run_workday_pass=_run_workday_pass,
        args=args,
        targets=targets,
    )
    persist_crawl_results(
        app=app,
        runtime_state=runtime_state,
        targets=targets,
        final_assessments=execution.final_assessments,
        refreshed_jobs=execution.refreshed_jobs,
        today_iso=date.today().isoformat(),
        search_cache=search_cache,
        non_greenhouse_cache=non_greenhouse_cache,
        greenhouse_assessments_by_key=execution.greenhouse_assessments_by_key,
        crawl_run=execution.crawl_run,
        phenom_run=execution.phenom_run,
        workday_run=execution.workday_run,
        registry_service_context=registry_service_context,
    )

    print_run_results(
        skipped_assessments=skipped_assessments,
        final_assessments=execution.final_assessments,
        refreshed_jobs=execution.refreshed_jobs,
    )
    return 0