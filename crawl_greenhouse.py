#!/usr/bin/env python3
"""
ATS-aware job crawler for a fixed list of target companies.

The crawler intentionally skips Gregslist and company-homepage discovery. It:
- generates likely Greenhouse board slugs for each target company
- probes the Greenhouse public jobs API until it finds a live board
- falls back to configured Workday boards when appropriate
- fetches job detail payloads for matched roles
- filters jobs by target title families
- writes a refreshed matched-jobs snapshot to crawler_cache/matched_jobs.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from urllib.error import HTTPError, URLError

from ats.app_bootstrap import build_default_bootstrap
from ats.cli_args import parse_args
from ats.common import clean_display_text, company_cache_key
from ats.runner import run_crawl


APP = build_default_bootstrap(clean_display_text=clean_display_text, company_cache_key=company_cache_key)

class CrawlError(RuntimeError):
    """Raised when crawling cannot proceed safely."""

async def run(
    args: argparse.Namespace,
) -> int:
    return await run_crawl(args, app=APP, crawl_error_type=CrawlError)


def main() -> int:
    args = parse_args(
        default_target_company_count=len(APP.default_target_companies),
        default_delay_seconds=APP.default_delay_seconds,
        default_concurrency=APP.default_concurrency,
        default_timeout_seconds=APP.default_timeout_seconds,
        default_workday_discovery_limit=APP.default_workday_discovery_limit,
        valid_job_tracking_statuses=APP.valid_job_tracking_statuses,
    )
    try:
        return asyncio.run(run(args))
    except CrawlError as exc:
        print(f"Crawl blocked: {exc}", file=sys.stderr)
        return 2
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
