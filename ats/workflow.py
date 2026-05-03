from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from .common import clean_display_text, company_cache_key, normalize_job_id
from .models import CompanyAssessment, MatchedJob
from .snapshot import load_matched_jobs_snapshot, matched_job_key


def parse_iso_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def build_non_greenhouse_revisit_record(company_name: str, last_checked: str, next_revisit: str) -> dict:
    return {
        "company_slug": company_cache_key(company_name),
        "company_name": company_name,
        "board_type": "ats_research",
        "last_checked": last_checked,
        "next_revisit": next_revisit,
        "reason": "Greenhouse board not found; investigate alternate ATS/job board.",
        "notes": "Check likely systems such as Workday, Lever, Ashby, SmartRecruiters, and direct company-hosted boards.",
    }


def sync_non_greenhouse_company_revisits(
    *,
    load_company_revisit_records,
    save_company_revisit_records,
    load_company_search_cache,
    load_non_greenhouse_companies,
    default_non_greenhouse_revisit_days: int,
    search_cache: dict[str, dict] | None = None,
    non_greenhouse_cache: dict[str, str] | None = None,
    today_iso: str | None = None,
) -> int:
    records = load_company_revisit_records()
    search_records = search_cache if search_cache is not None else load_company_search_cache()
    non_greenhouse_companies = (
        non_greenhouse_cache if non_greenhouse_cache is not None else load_non_greenhouse_companies()
    )
    fallback_date = today_iso or date.today().isoformat()
    created = 0

    for company_key, company_name in non_greenhouse_companies.items():
        existing = records.get(company_key)
        if existing is not None:
            continue

        search_record = search_records.get(company_key, {})
        last_checked = clean_display_text(str(search_record.get("last_scraped") or "")) or fallback_date
        parsed_last_checked = parse_iso_date(last_checked) or parse_iso_date(fallback_date) or date.today()
        next_revisit = (parsed_last_checked + timedelta(days=default_non_greenhouse_revisit_days)).isoformat()
        records[company_key] = build_non_greenhouse_revisit_record(
            company_name=company_name,
            last_checked=last_checked,
            next_revisit=next_revisit,
        )
        created += 1

    if created:
        save_company_revisit_records(records)
    return created


def get_matched_job_snapshot_record(company_slug: str, greenhouse_job_id: str, *, matched_jobs_path: Path) -> MatchedJob | None:
    for job in load_matched_jobs_snapshot(matched_jobs_path):
        if matched_job_key(job.company_slug, job.greenhouse_job_id) == (company_slug, greenhouse_job_id):
            return job
    return None


def upsert_job_tracking_record(
    *,
    company_slug: str,
    greenhouse_job_id: str,
    status: str,
    review_date: str | None,
    application_date: str | None,
    next_action_date: str | None,
    notes: str | None,
    match_rationale: str | None,
    valid_job_tracking_statuses: tuple[str, ...],
    crawl_error_type: type[Exception],
    load_job_tracking_records,
    save_job_tracking_records,
    matched_jobs_path: Path,
) -> dict:
    if status not in valid_job_tracking_statuses:
        raise crawl_error_type(f"Unsupported job status: {status}")

    records = load_job_tracking_records()
    normalized_job_id = normalize_job_id(greenhouse_job_id)
    key = matched_job_key(company_slug, normalized_job_id)
    existing = records.get(key)
    snapshot_job = get_matched_job_snapshot_record(company_slug, normalized_job_id, matched_jobs_path=matched_jobs_path)
    if existing is None and snapshot_job is None:
        raise crawl_error_type(
            f"Job {greenhouse_job_id} for company slug '{company_slug}' was not found in the current snapshot or tracking overlay."
        )

    today_iso = date.today().isoformat()
    base_record = existing or {
        "company_slug": company_slug,
        "greenhouse_job_id": normalized_job_id,
        "job_url": snapshot_job.job_url if snapshot_job is not None else "",
        "status": "pending_review",
        "review_date": "",
        "application_date": "",
        "next_action_date": "",
        "notes": "",
        "match_rationale": "",
    }

    updated = {
        **base_record,
        "status": status,
        "job_url": base_record.get("job_url") or (snapshot_job.job_url if snapshot_job is not None else ""),
        "review_date": review_date if review_date is not None else (base_record.get("review_date") or today_iso),
        "application_date": application_date if application_date is not None else base_record.get("application_date", ""),
        "next_action_date": next_action_date if next_action_date is not None else base_record.get("next_action_date", ""),
        "notes": notes if notes is not None else base_record.get("notes", ""),
        "match_rationale": match_rationale if match_rationale is not None else base_record.get("match_rationale", ""),
    }

    if status == "applied" and not updated["application_date"]:
        updated["application_date"] = today_iso
    if status != "applied" and application_date == "":
        updated["application_date"] = ""

    records[key] = updated
    save_job_tracking_records(records)
    return updated


def backfill_pending_review_records(
    *,
    review_date: str | None,
    notes: str | None,
    match_rationale: str | None,
    load_job_tracking_records,
    save_job_tracking_records,
    matched_jobs_path: Path,
) -> int:
    tracked_records = load_job_tracking_records()
    matched_jobs = load_matched_jobs_snapshot(matched_jobs_path)
    today_iso = date.today().isoformat()
    created = 0

    for job in matched_jobs:
        key = matched_job_key(job.company_slug, job.greenhouse_job_id)
        if key in tracked_records:
            continue
        tracked_records[key] = {
            "company_slug": job.company_slug,
            "greenhouse_job_id": job.greenhouse_job_id,
            "job_url": job.job_url,
            "status": "pending_review",
            "review_date": review_date if review_date is not None else today_iso,
            "application_date": "",
            "next_action_date": "",
            "notes": notes if notes is not None else "Backfilled from matched_jobs.jsonl snapshot.",
            "match_rationale": match_rationale if match_rationale is not None else "Auto-backfilled pending-review record for an existing matched job.",
        }
        created += 1

    if created:
        save_job_tracking_records(tracked_records)
    return created


def build_cached_assessment(company_name: str, record: dict, status: str) -> CompanyAssessment:
    resolved_slug = clean_display_text(str(record.get("resolved_slug") or ""))
    board_url = clean_display_text(str(record.get("board_url") or ""))
    source = clean_display_text(str(record.get("source") or "greenhouse")) or "greenhouse"
    jobs_seen = record.get("jobs_seen")
    matched_job_count = record.get("matched_job_count")
    matched_jobs = [None] * matched_job_count if isinstance(matched_job_count, int) and matched_job_count > 0 else []
    return CompanyAssessment(
        name=company_name,
        attempted_slugs=[],
        resolved_slug=resolved_slug or None,
        board_url=board_url or None,
        status=status,
        source=source,
        jobs_seen=jobs_seen if isinstance(jobs_seen, int) else 0,
        matched_jobs=matched_jobs,
    )


def build_search_record(assessment: CompanyAssessment, today_iso: str) -> dict:
    return {
        "company_name": assessment.name,
        "last_scraped": today_iso,
        "board_url": assessment.board_url,
        "resolved_slug": assessment.resolved_slug,
        "jobs_seen": assessment.jobs_seen,
        "matched_job_count": len(assessment.matched_jobs),
        "status": assessment.status,
        "source": assessment.source,
    }