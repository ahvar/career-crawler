from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable

from .common import clean_display_text, company_cache_key
from .models import CompanyAssessment


def normalize_company_registry_record(record: dict) -> dict | None:
    company_slug = clean_display_text(str(record.get("company_slug") or ""))
    company_name = clean_display_text(str(record.get("company_name") or ""))
    if not company_slug or not company_name:
        return None
    return {
        "company_slug": company_slug,
        "company_name": company_name,
        "primary_ats": clean_display_text(str(record.get("primary_ats") or "unknown")) or "unknown",
        "greenhouse_status": clean_display_text(str(record.get("greenhouse_status") or "unknown")) or "unknown",
        "greenhouse_board_url": clean_display_text(str(record.get("greenhouse_board_url") or "")),
        "greenhouse_slug": clean_display_text(str(record.get("greenhouse_slug") or "")),
        "greenhouse_last_checked": clean_display_text(str(record.get("greenhouse_last_checked") or "")),
        "greenhouse_status_detail": clean_display_text(str(record.get("greenhouse_status_detail") or "")),
        "workday_status": clean_display_text(str(record.get("workday_status") or "unknown")) or "unknown",
        "workday_board_url": clean_display_text(str(record.get("workday_board_url") or "")),
        "workday_tenant": clean_display_text(str(record.get("workday_tenant") or "")),
        "workday_site_id": clean_display_text(str(record.get("workday_site_id") or "")),
        "workday_last_checked": clean_display_text(str(record.get("workday_last_checked") or "")),
        "workday_status_detail": clean_display_text(str(record.get("workday_status_detail") or "")),
        "other_ats_status": clean_display_text(str(record.get("other_ats_status") or "unknown")) or "unknown",
        "other_ats_board_url": clean_display_text(str(record.get("other_ats_board_url") or "")),
        "other_ats_last_checked": clean_display_text(str(record.get("other_ats_last_checked") or "")),
        "other_ats_status_detail": clean_display_text(str(record.get("other_ats_status_detail") or "")),
        "last_overall_check": clean_display_text(str(record.get("last_overall_check") or "")),
        "next_action": clean_display_text(str(record.get("next_action") or "no_action")) or "no_action",
        "next_action_date": clean_display_text(str(record.get("next_action_date") or "")),
        "revisit_board_type": clean_display_text(str(record.get("revisit_board_type") or "")),
        "revisit_reason": clean_display_text(str(record.get("revisit_reason") or "")),
        "notes": clean_display_text(str(record.get("notes") or "")),
    }


def make_default_company_registry_record(
    company_slug: str,
    company_name: str,
    workday_board_hints: dict[str, dict],
) -> dict:
    workday_hint = workday_board_hints.get(company_slug, {})
    return {
        "company_slug": company_slug,
        "company_name": company_name,
        "primary_ats": "unknown",
        "greenhouse_status": "unknown",
        "greenhouse_board_url": "",
        "greenhouse_slug": "",
        "greenhouse_last_checked": "",
        "greenhouse_status_detail": "",
        "workday_status": "confirmed" if workday_hint else "unknown",
        "workday_board_url": clean_display_text(str(workday_hint.get("board_url") or "")),
        "workday_tenant": clean_display_text(str(workday_hint.get("tenant") or "")),
        "workday_site_id": clean_display_text(str(workday_hint.get("site_id") or "")),
        "workday_last_checked": "",
        "workday_status_detail": "",
        "other_ats_status": "unknown",
        "other_ats_board_url": "",
        "other_ats_last_checked": "",
        "other_ats_status_detail": "",
        "last_overall_check": "",
        "next_action": "no_action",
        "next_action_date": "",
        "revisit_board_type": "",
        "revisit_reason": "",
        "notes": "",
    }


def greenhouse_status_from_assessment_status(status: str) -> str:
    if status == "Greenhouse board not found":
        return "not_found"
    if status.startswith("Network error"):
        return "needs_retry"
    if status.startswith("Skipped"):
        return "unknown"
    return "confirmed"


def workday_status_from_assessment_status(status: str) -> str:
    if status == "Workday board not configured":
        return "unknown"
    if status.startswith("Network error"):
        return "needs_retry"
    if status.startswith("Skipped"):
        return "unknown"
    return "confirmed"


def other_ats_status_from_assessment_status(status: str) -> str:
    if status == "Phenom board not configured":
        return "unknown"
    if status.startswith("Network error"):
        return "needs_retry"
    if status.startswith("Skipped"):
        return "unknown"
    return "confirmed"


def apply_company_assessment_to_registry_record(record: dict, assessment: CompanyAssessment, checked_at: str) -> None:
    record["company_name"] = clean_display_text(assessment.name) or record["company_name"]
    record["last_overall_check"] = checked_at
    if assessment.source == "workday":
        record["workday_status"] = workday_status_from_assessment_status(assessment.status)
        record["workday_board_url"] = clean_display_text(str(assessment.board_url or "")) or record["workday_board_url"]
        record["workday_last_checked"] = checked_at
        record["workday_status_detail"] = assessment.status
    elif assessment.source == "greenhouse":
        record["greenhouse_status"] = greenhouse_status_from_assessment_status(assessment.status)
        record["greenhouse_board_url"] = clean_display_text(str(assessment.board_url or "")) or record["greenhouse_board_url"]
        record["greenhouse_slug"] = clean_display_text(str(assessment.resolved_slug or "")) or record["greenhouse_slug"]
        record["greenhouse_last_checked"] = checked_at
        record["greenhouse_status_detail"] = assessment.status
    else:
        record["other_ats_status"] = other_ats_status_from_assessment_status(assessment.status)
        record["other_ats_board_url"] = clean_display_text(str(assessment.board_url or "")) or record["other_ats_board_url"]
        record["other_ats_last_checked"] = checked_at
        record["other_ats_status_detail"] = assessment.status


def finalize_company_registry_record(record: dict, revisit_record: dict | None) -> dict:
    greenhouse_status = record["greenhouse_status"]
    workday_status = record["workday_status"]
    other_ats_status = record["other_ats_status"]

    if greenhouse_status == "confirmed":
        record["primary_ats"] = "greenhouse"
    elif workday_status == "confirmed":
        record["primary_ats"] = "workday"
    elif other_ats_status == "confirmed":
        record["primary_ats"] = "other"
    elif greenhouse_status == "not_found" and workday_status == "not_found":
        record["primary_ats"] = "none"
    else:
        record["primary_ats"] = "unknown"

    record["revisit_board_type"] = clean_display_text(str((revisit_record or {}).get("board_type") or ""))
    record["revisit_reason"] = clean_display_text(str((revisit_record or {}).get("reason") or ""))
    record["notes"] = clean_display_text(str((revisit_record or {}).get("notes") or ""))
    record["next_action_date"] = clean_display_text(str((revisit_record or {}).get("next_revisit") or ""))

    if record["primary_ats"] == "greenhouse":
        record["next_action"] = "no_action"
    elif record["primary_ats"] == "workday":
        record["next_action"] = "review_workday"
    elif record["primary_ats"] == "other":
        record["next_action"] = "review_other_ats"
    elif greenhouse_status == "not_found" and workday_status == "unknown":
        record["next_action"] = "check_workday"
    elif revisit_record is not None:
        record["next_action"] = "check_other_ats"
    else:
        record["next_action"] = "no_action"

    return record


def build_company_registry_records(
    *,
    search_records: dict[str, dict],
    non_greenhouse_records: dict[str, str],
    revisit_records: dict[str, dict],
    registry_records: dict[str, dict],
    default_company_names: Iterable[str],
    workday_board_hints: dict[str, dict],
    greenhouse_assessments: Iterable[CompanyAssessment] = (),
    workday_assessments: Iterable[CompanyAssessment] = (),
    other_ats_assessments: Iterable[CompanyAssessment] = (),
) -> dict[str, dict]:
    company_keys = set(registry_records)
    company_keys.update(search_records)
    company_keys.update(non_greenhouse_records)
    company_keys.update(revisit_records)
    company_keys.update(workday_board_hints)
    company_keys.update(company_cache_key(company_name) for company_name in default_company_names)

    normalized_records: dict[str, dict] = {}
    for company_key in company_keys:
        search_record = search_records.get(company_key, {})
        revisit_record = revisit_records.get(company_key)
        existing_record = registry_records.get(company_key)
        company_name = clean_display_text(
            str(
                search_record.get("company_name")
                or (revisit_record or {}).get("company_name")
                or non_greenhouse_records.get(company_key)
                or (existing_record or {}).get("company_name")
                or company_key
            )
        )
        record = normalize_company_registry_record(existing_record or {}) if existing_record else None
        if record is None:
            record = make_default_company_registry_record(company_key, company_name, workday_board_hints)
        else:
            default_record = make_default_company_registry_record(company_key, company_name, workday_board_hints)
            record = {**default_record, **record, "company_name": company_name, "company_slug": company_key}

        if company_key in non_greenhouse_records and record["greenhouse_status"] == "unknown":
            record["greenhouse_status"] = "not_found"

        if search_record:
            last_scraped = clean_display_text(str(search_record.get("last_scraped") or ""))
            record["last_overall_check"] = last_scraped or record["last_overall_check"]
            source = clean_display_text(str(search_record.get("source") or "greenhouse")) or "greenhouse"
            status = clean_display_text(str(search_record.get("status") or ""))
            if source == "workday":
                record["workday_status"] = workday_status_from_assessment_status(status)
                record["workday_board_url"] = clean_display_text(str(search_record.get("board_url") or "")) or record["workday_board_url"]
                record["workday_last_checked"] = last_scraped or record["workday_last_checked"]
                record["workday_status_detail"] = status or record["workday_status_detail"]
            elif source == "greenhouse":
                record["greenhouse_status"] = greenhouse_status_from_assessment_status(status)
                record["greenhouse_board_url"] = clean_display_text(str(search_record.get("board_url") or "")) or record["greenhouse_board_url"]
                record["greenhouse_slug"] = clean_display_text(str(search_record.get("resolved_slug") or "")) or record["greenhouse_slug"]
                record["greenhouse_last_checked"] = last_scraped or record["greenhouse_last_checked"]
                record["greenhouse_status_detail"] = status or record["greenhouse_status_detail"]
            else:
                record["other_ats_status"] = other_ats_status_from_assessment_status(status)
                record["other_ats_board_url"] = clean_display_text(str(search_record.get("board_url") or "")) or record["other_ats_board_url"]
                record["other_ats_last_checked"] = last_scraped or record["other_ats_last_checked"]
                record["other_ats_status_detail"] = status or record["other_ats_status_detail"]

        normalized_records[company_key] = finalize_company_registry_record(record, revisit_record)

    for assessment in greenhouse_assessments:
        company_key = company_cache_key(assessment.name)
        record = normalized_records.get(company_key) or make_default_company_registry_record(
            company_key,
            assessment.name,
            workday_board_hints,
        )
        checked_at = clean_display_text(str(record.get("last_overall_check") or "")) or date.today().isoformat()
        apply_company_assessment_to_registry_record(record, assessment, checked_at)
        normalized_records[company_key] = finalize_company_registry_record(record, revisit_records.get(company_key))

    for assessment in workday_assessments:
        company_key = company_cache_key(assessment.name)
        record = normalized_records.get(company_key) or make_default_company_registry_record(
            company_key,
            assessment.name,
            workday_board_hints,
        )
        checked_at = clean_display_text(str(record.get("last_overall_check") or "")) or date.today().isoformat()
        apply_company_assessment_to_registry_record(record, assessment, checked_at)
        normalized_records[company_key] = finalize_company_registry_record(record, revisit_records.get(company_key))

    for assessment in other_ats_assessments:
        company_key = company_cache_key(assessment.name)
        record = normalized_records.get(company_key) or make_default_company_registry_record(
            company_key,
            assessment.name,
            workday_board_hints,
        )
        checked_at = clean_display_text(str(record.get("last_overall_check") or "")) or date.today().isoformat()
        apply_company_assessment_to_registry_record(record, assessment, checked_at)
        normalized_records[company_key] = finalize_company_registry_record(record, revisit_records.get(company_key))

    return normalized_records


def categorize_company_registry_records(records: dict[str, dict]) -> dict[str, list[dict]]:
    categories = {
        "confirmed_greenhouse": [],
        "confirmed_workday": [],
        "confirmed_other_ats": [],
        "greenhouse_not_found_workday_unchecked": [],
        "neither_confirmed": [],
        "unknown": [],
    }

    for record in records.values():
        greenhouse_status = record["greenhouse_status"]
        workday_status = record["workday_status"]
        if greenhouse_status == "confirmed":
            categories["confirmed_greenhouse"].append(record)
        elif workday_status == "confirmed":
            categories["confirmed_workday"].append(record)
        elif record["other_ats_status"] == "confirmed":
            categories["confirmed_other_ats"].append(record)
        elif greenhouse_status == "not_found" and workday_status == "unknown":
            categories["greenhouse_not_found_workday_unchecked"].append(record)
        elif greenhouse_status == "not_found" and workday_status == "not_found":
            categories["neither_confirmed"].append(record)
        else:
            categories["unknown"].append(record)

    for bucket in categories.values():
        bucket.sort(key=lambda item: item["company_name"].casefold())
    return categories


def get_workday_check_candidates(records: dict[str, dict]) -> list[dict]:
    candidates = [record for record in records.values() if record["next_action"] == "check_workday"]
    candidates.sort(key=lambda item: (item["next_action_date"], item["company_name"].casefold()))
    return candidates


def load_company_names_from_text_file(path: Path) -> list[str]:
    if not path.exists():
        return []

    company_names: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        company_name = clean_display_text(line)
        if not company_name or company_name.startswith("#"):
            continue
        company_key = company_cache_key(company_name)
        if company_key in seen:
            continue
        seen.add(company_key)
        company_names.append(company_name)
    return company_names