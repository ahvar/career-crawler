from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from .snapshot import load_matched_jobs_snapshot


@dataclass(frozen=True)
class TrackingServiceContext:
    matched_jobs_path: Path
    load_job_tracking_records: Callable[[], dict[tuple[str, str], dict]]
    load_company_revisit_records: Callable[[], dict[str, dict]]
    render_tracking_report: Callable[..., str]


def format_tracking_report(context: TrackingServiceContext) -> str:
    return context.render_tracking_report(
        today=date.today(),
        matched_jobs=load_matched_jobs_snapshot(context.matched_jobs_path),
        tracked_jobs=context.load_job_tracking_records(),
        company_revisits=context.load_company_revisit_records(),
    )