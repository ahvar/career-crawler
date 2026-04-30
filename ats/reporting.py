from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .common import company_cache_key
from .models import CompanyAssessment, MatchedJob
from .registry import get_workday_check_candidates


def format_results(rows: Iterable[CompanyAssessment]) -> str:
    results = list(rows)
    if not results:
        return "No company results were collected."

    company_width = max(len("Company"), *(len(result.name) for result in results))
    slug_cells = [result.resolved_slug or "-" for result in results]
    slug_width = max(len("Slug"), *(len(cell) for cell in slug_cells))
    jobs_width = max(len("Jobs"), *(len(str(result.jobs_seen)) for result in results))
    matches_width = max(len("Matches"), *(len(str(len(result.matched_jobs))) for result in results))
    status_width = max(len("Status"), *(len(result.status) for result in results))

    lines = [
        f"{'Company'.ljust(company_width)}  "
        f"{'Slug'.ljust(slug_width)}  "
        f"{'Jobs'.rjust(jobs_width)}  "
        f"{'Matches'.rjust(matches_width)}  "
        f"{'Status'.ljust(status_width)}",
        f"{'-' * company_width}  {'-' * slug_width}  {'-' * jobs_width}  {'-' * matches_width}  {'-' * status_width}",
    ]
    for result, slug_cell in zip(results, slug_cells):
        lines.append(
            f"{result.name.ljust(company_width)}  "
            f"{slug_cell.ljust(slug_width)}  "
            f"{str(result.jobs_seen).rjust(jobs_width)}  "
            f"{str(len(result.matched_jobs)).rjust(matches_width)}  "
            f"{result.status.ljust(status_width)}"
        )
    return "\n".join(lines)


def format_matched_jobs(jobs: Iterable[MatchedJob]) -> str:
    job_list = list(jobs)
    if not job_list:
        return ""

    company_width = max(len("Company"), *(len(job.company_name) for job in job_list))
    title_width = max(len("Job Title"), *(len(job.job_title) for job in job_list))
    location_width = max(len("Location"), *(len(job.job_location or "-") for job in job_list))
    url_width = max(len("Job URL"), *(len(job.job_url) for job in job_list))

    lines = [
        "",
        "Matched Jobs",
        f"{'Company'.ljust(company_width)}  {'Job Title'.ljust(title_width)}  {'Location'.ljust(location_width)}  {'Job URL'.ljust(url_width)}",
        f"{'-' * company_width}  {'-' * title_width}  {'-' * location_width}  {'-' * url_width}",
    ]
    for job in job_list:
        lines.append(
            f"{job.company_name.ljust(company_width)}  "
            f"{job.job_title.ljust(title_width)}  "
            f"{(job.job_location or '-').ljust(location_width)}  "
            f"{job.job_url.ljust(url_width)}"
        )
    return "\n".join(lines)


def format_matched_job_urls(jobs: Iterable[MatchedJob]) -> str:
    job_list = list(jobs)
    if not job_list:
        return ""

    lines = ["", "Matched Job URLs"]
    lines.extend(job.job_url for job in job_list)
    return "\n".join(lines)


def format_company_ats_report(records: dict[str, dict], categories: dict[str, list[dict]]) -> str:
    workday_candidates = get_workday_check_candidates(records)
    other_ats_candidates = [record for record in records.values() if record.get("next_action") == "check_other_ats"]
    other_ats_candidates.sort(key=lambda item: (item.get("next_action_date", ""), item["company_name"].casefold()))
    lines = [
        "Company ATS Report",
        f"Registry records: {len(records)}",
        f"Confirmed Greenhouse companies: {len(categories['confirmed_greenhouse'])}",
        f"Confirmed Workday companies: {len(categories['confirmed_workday'])}",
        f"Confirmed Other ATS companies: {len(categories['confirmed_other_ats'])}",
        f"Greenhouse not found, Workday unchecked: {len(categories['greenhouse_not_found_workday_unchecked'])}",
        f"Neither confirmed: {len(categories['neither_confirmed'])}",
        f"Unknown/mixed: {len(categories['unknown'])}",
        "",
        "Workday Check Candidates",
    ]

    if workday_candidates:
        for record in workday_candidates:
            details = [record["company_name"]]
            if record["next_action_date"]:
                details.append(f"next action {record['next_action_date']}")
            if record["revisit_reason"]:
                details.append(record["revisit_reason"])
            lines.append(f"- {'; '.join(details)}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Other ATS Follow-Up Candidates")
    if other_ats_candidates:
        for record in other_ats_candidates:
            details = [record["company_name"]]
            if record.get("next_action_date"):
                details.append(f"next action {record['next_action_date']}")
            if record.get("revisit_reason"):
                details.append(record["revisit_reason"])
            lines.append(f"- {'; '.join(details)}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Confirmed Other ATS Companies")
    if categories["confirmed_other_ats"]:
        for record in categories["confirmed_other_ats"]:
            details = [record["company_name"]]
            if record.get("other_ats_board_url"):
                details.append(record["other_ats_board_url"])
            lines.append(f"- {'; '.join(details)}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Confirmed Workday Companies")
    if categories["confirmed_workday"]:
        for record in categories["confirmed_workday"]:
            details = [record["company_name"]]
            if record["workday_board_url"]:
                details.append(record["workday_board_url"])
            lines.append(f"- {'; '.join(details)}")
    else:
        lines.append("- none")

    return "\n".join(lines)


def format_intake_workday_report(records: dict[str, dict], company_names: list[str], path: Path) -> str:
    intake_records: list[dict] = []
    missing_records: list[str] = []
    for company_name in company_names:
        record = records.get(company_cache_key(company_name))
        if record is None:
            missing_records.append(company_name)
            continue
        intake_records.append(record)

    confirmed_greenhouse = [record for record in intake_records if record["primary_ats"] == "greenhouse"]
    confirmed_workday = [record for record in intake_records if record["primary_ats"] == "workday"]
    workday_candidates = [record for record in intake_records if record["next_action"] == "check_workday"]
    other = [
        record for record in intake_records
        if record["primary_ats"] not in {"greenhouse", "workday"} and record["next_action"] != "check_workday"
    ]

    workday_candidates.sort(key=lambda item: (item["next_action_date"], item["company_name"].casefold()))
    confirmed_greenhouse.sort(key=lambda item: item["company_name"].casefold())
    confirmed_workday.sort(key=lambda item: item["company_name"].casefold())
    other.sort(key=lambda item: item["company_name"].casefold())

    lines = [
        f"Intake ATS Report: {path}",
        f"Intake companies: {len(company_names)}",
        f"Confirmed Greenhouse in intake: {len(confirmed_greenhouse)}",
        f"Confirmed Workday in intake: {len(confirmed_workday)}",
        f"Workday check candidates in intake: {len(workday_candidates)}",
        f"Other intake states: {len(other)}",
    ]

    if missing_records:
        lines.append(f"Missing from registry: {len(missing_records)}")

    lines.append("")
    lines.append("Top Workday Candidates From Intake")
    if workday_candidates:
        for record in workday_candidates[:25]:
            details = [record["company_name"]]
            if record["next_action_date"]:
                details.append(f"next action {record['next_action_date']}")
            if record["revisit_reason"]:
                details.append(record["revisit_reason"])
            lines.append(f"- {'; '.join(details)}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Confirmed Greenhouse Intake Companies")
    if confirmed_greenhouse:
        for record in confirmed_greenhouse:
            detail = record["greenhouse_status_detail"] or record["greenhouse_board_url"]
            lines.append(f"- {record['company_name']}; {detail}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Confirmed Workday Intake Companies")
    if confirmed_workday:
        for record in confirmed_workday:
            detail = record["workday_board_url"] or record["workday_status_detail"]
            lines.append(f"- {record['company_name']}; {detail}")
    else:
        lines.append("- none")

    if missing_records:
        lines.append("")
        lines.append("Missing Intake Companies")
        for company_name in missing_records:
            lines.append(f"- {company_name}")

    return "\n".join(lines)


def format_workday_discovery_report(results: list[dict], *, applied: bool) -> str:
    lines = [
        "Workday Discovery Report",
        f"Candidates checked: {len(results)}",
        f"Boards confirmed: {sum(1 for result in results if result['status'] == 'confirmed')}",
        f"Boards not found: {sum(1 for result in results if result['status'] == 'not_found')}",
        f"Needs retry: {sum(1 for result in results if result['status'] == 'needs_retry')}",
        f"Errors: {sum(1 for result in results if result['status'] == 'error')}",
        f"Apply mode: {'on' if applied else 'off'}",
        "",
        "Discovery Results",
    ]

    if not results:
        lines.append("- none")
        return "\n".join(lines)

    for result in results:
        details = [result["company_name"], result["status"]]
        if result.get("board_url"):
            details.append(result["board_url"])
        if result.get("detail"):
            details.append(result["detail"])
        lines.append(f"- {'; '.join(details)}")

    return "\n".join(lines)
