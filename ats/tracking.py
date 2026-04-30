from __future__ import annotations

from datetime import date

from .models import MatchedJob


def _parse_iso_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def format_tracking_report(
    *,
    today: date,
    matched_jobs: list[MatchedJob],
    tracked_jobs: dict[tuple[str, str], dict],
    company_revisits: dict[str, dict],
) -> str:
    matched_jobs_by_key = {
        (job.company_slug, job.greenhouse_job_id): job
        for job in matched_jobs
    }
    jobs_with_tracking: list[tuple[MatchedJob, dict]] = []
    missing_jobs: list[dict] = []
    for key, record in tracked_jobs.items():
        matched_job = matched_jobs_by_key.get(key)
        if matched_job is None:
            missing_jobs.append(record)
        else:
            jobs_with_tracking.append((matched_job, record))

    status_counts: dict[str, int] = {}
    for record in tracked_jobs.values():
        status = record["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    due_companies = [
        record for record in company_revisits.values()
        if (due_date := _parse_iso_date(record["next_revisit"])) is not None and due_date <= today
    ]
    upcoming_companies = [
        record for record in company_revisits.values()
        if (due_date := _parse_iso_date(record["next_revisit"])) is not None and due_date > today
    ]
    due_companies.sort(key=lambda record: record["next_revisit"])
    upcoming_companies.sort(key=lambda record: record["next_revisit"])

    lines = [
        "Tracking Report",
        f"Today: {today.isoformat()}",
        f"Matched jobs snapshot: {len(matched_jobs)}",
        f"Tracked jobs: {len(tracked_jobs)}",
        f"Tracked companies with revisit dates: {len(company_revisits)}",
    ]

    if status_counts:
        lines.append("Tracked job statuses:")
        for status in sorted(status_counts):
            lines.append(f"- {status}: {status_counts[status]}")
    else:
        lines.append("Tracked job statuses: none yet")

    lines.append("")
    lines.append("Tracked Jobs In Current Snapshot")
    if jobs_with_tracking:
        for job, record in sorted(jobs_with_tracking, key=lambda item: (item[1]["status"], item[0].company_name, item[0].job_title)):
            details = [
                f"{record['status']}",
                f"{job.company_name} | {job.job_title}",
            ]
            if record["next_action_date"]:
                details.append(f"next action {record['next_action_date']}")
            if record["notes"]:
                details.append(record["notes"])
            lines.append(f"- {'; '.join(details)}")
            lines.append(f"  {job.job_url}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Tracked Jobs Missing From Current Snapshot")
    if missing_jobs:
        for record in sorted(missing_jobs, key=lambda item: (item["status"], item["company_slug"], item["greenhouse_job_id"])):
            details = [
                record["status"],
                f"{record['company_slug']} | {record['greenhouse_job_id']}",
            ]
            if record["next_action_date"]:
                details.append(f"next action {record['next_action_date']}")
            if record["notes"]:
                details.append(record["notes"])
            lines.append(f"- {'; '.join(details)}")
            if record["job_url"]:
                lines.append(f"  {record['job_url']}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Companies Due For Revisit")
    if due_companies:
        for record in due_companies:
            details = [
                record["company_name"],
                f"board={record['board_type']}",
                f"next revisit {record['next_revisit']}",
            ]
            if record["reason"]:
                details.append(record["reason"])
            lines.append(f"- {'; '.join(details)}")
    else:
        lines.append("- none due today")

    lines.append("")
    lines.append("Upcoming Company Revisits")
    if upcoming_companies:
        for record in upcoming_companies:
            details = [
                record["company_name"],
                f"board={record['board_type']}",
                f"next revisit {record['next_revisit']}",
            ]
            if record["reason"]:
                details.append(record["reason"])
            lines.append(f"- {'; '.join(details)}")
    else:
        lines.append("- none scheduled")

    return "\n".join(lines)