from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .common import canonical_company_name, clean_display_text, company_cache_key, normalize_job_id
from .registry import normalize_company_registry_record


def atomic_write(path: Path, text: str) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)


def count_jsonl_rows(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def count_text_rows(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def load_jsonl_records(path: Path) -> list[dict]:
    if not path.exists():
        return []

    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def save_jsonl_records(path: Path, records: Iterable[dict]) -> int:
    serialized_lines = [json.dumps(record, sort_keys=True) for record in records]
    text = "\n".join(serialized_lines)
    if text:
        text += "\n"
    atomic_write(path, text)
    return len(serialized_lines)


def choose_latest_record(existing: dict | None, candidate: dict) -> dict:
    if existing is None:
        return candidate
    existing_date = clean_display_text(str(existing.get("last_scraped") or existing.get("last_overall_check") or ""))
    candidate_date = clean_display_text(str(candidate.get("last_scraped") or candidate.get("last_overall_check") or ""))
    if candidate_date >= existing_date:
        return candidate
    return existing


def merge_status(existing_status: str, candidate_status: str) -> str:
    status_rank = {
        "unknown": 0,
        "needs_retry": 1,
        "not_found": 2,
        "confirmed": 3,
    }
    existing_status = clean_display_text(existing_status) or "unknown"
    candidate_status = clean_display_text(candidate_status) or "unknown"
    return candidate_status if status_rank.get(candidate_status, 0) >= status_rank.get(existing_status, 0) else existing_status


def merge_company_registry_records(existing: dict | None, candidate: dict) -> dict:
    if existing is None:
        return candidate

    merged = {**existing}
    for key, value in candidate.items():
        if value not in ("", None):
            merged[key] = value

    for status_key in ("greenhouse_status", "workday_status"):
        merged[status_key] = merge_status(existing.get(status_key, ""), candidate.get(status_key, ""))

    for detail_key in ("greenhouse_status_detail", "workday_status_detail"):
        candidate_date_key = detail_key.replace("status_detail", "last_checked")
        candidate_date = clean_display_text(str(candidate.get(candidate_date_key) or ""))
        existing_date = clean_display_text(str(existing.get(candidate_date_key) or ""))
        if existing_date and existing_date > candidate_date:
            merged[detail_key] = existing.get(detail_key, "")

    return merged


def normalize_job_tracking_record(record: dict) -> dict | None:
    company_slug = clean_display_text(str(record.get("company_slug") or ""))
    greenhouse_job_id = normalize_job_id(record.get("greenhouse_job_id"))
    if not company_slug or not greenhouse_job_id:
        return None
    return {
        "company_slug": company_slug,
        "greenhouse_job_id": greenhouse_job_id,
        "job_url": clean_display_text(str(record.get("job_url") or "")),
        "status": clean_display_text(str(record.get("status") or "pending_review")) or "pending_review",
        "review_date": clean_display_text(str(record.get("review_date") or "")),
        "application_date": clean_display_text(str(record.get("application_date") or "")),
        "next_action_date": clean_display_text(str(record.get("next_action_date") or "")),
        "notes": clean_display_text(str(record.get("notes") or "")),
        "match_rationale": clean_display_text(str(record.get("match_rationale") or "")),
    }


def load_job_tracking_records(path: Path) -> dict[tuple[str, str], dict]:
    records: dict[tuple[str, str], dict] = {}
    for record in load_jsonl_records(path):
        normalized = normalize_job_tracking_record(record)
        if normalized is None:
            continue
        records[(normalized["company_slug"], normalized["greenhouse_job_id"])] = normalized
    return records


def save_job_tracking_records(path: Path, records: dict[tuple[str, str], dict]) -> int:
    serialized = [records[key] for key in sorted(records, key=lambda item: (item[0], item[1]))]
    return save_jsonl_records(path, serialized)


def normalize_company_revisit_record(record: dict) -> dict | None:
    company_name = canonical_company_name(str(record.get("company_name") or ""))
    company_slug = company_cache_key(company_name or str(record.get("company_slug") or ""))
    if not company_slug or not company_name:
        return None
    return {
        "company_slug": company_slug,
        "company_name": company_name,
        "board_type": clean_display_text(str(record.get("board_type") or "unknown")) or "unknown",
        "last_checked": clean_display_text(str(record.get("last_checked") or "")),
        "next_revisit": clean_display_text(str(record.get("next_revisit") or "")),
        "reason": clean_display_text(str(record.get("reason") or "")),
        "notes": clean_display_text(str(record.get("notes") or "")),
    }


def load_company_revisit_records(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for record in load_jsonl_records(path):
        normalized = normalize_company_revisit_record(record)
        if normalized is None:
            continue
        records[normalized["company_slug"]] = normalized
    return records


def save_company_revisit_records(path: Path, records: dict[str, dict]) -> int:
    serialized = [
        records[key]
        for key in sorted(records, key=lambda item: records[item].get("company_name", "").casefold())
    ]
    return save_jsonl_records(path, serialized)


def load_company_registry_records(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for record in load_jsonl_records(path):
        normalized = normalize_company_registry_record(record)
        if normalized is None:
            continue
        company_name = canonical_company_name(normalized["company_name"])
        company_slug = company_cache_key(company_name or normalized["company_slug"])
        if not company_slug:
            continue
        normalized = {**normalized, "company_slug": company_slug, "company_name": company_name or normalized["company_name"]}
        existing = records.get(company_slug)
        records[company_slug] = merge_company_registry_records(existing, normalized) if existing else normalized
    return records


def save_company_registry_records(path: Path, records: dict[str, dict]) -> int:
    serialized = [
        records[key]
        for key in sorted(records, key=lambda item: records[item].get("company_name", "").casefold())
    ]
    return save_jsonl_records(path, serialized)


def load_company_search_cache(path: Path) -> dict[str, dict]:
    records_by_company: dict[str, dict] = {}
    for record in load_jsonl_records(path):
        company_name = canonical_company_name(str(record.get("company_name") or ""))
        if not company_name:
            continue
        normalized_record = {**record, "company_name": company_name}
        company_key = company_cache_key(company_name)
        existing = records_by_company.get(company_key)
        records_by_company[company_key] = choose_latest_record(existing, normalized_record) if existing else normalized_record
    return records_by_company


def save_company_search_cache(path: Path, records_by_company: dict[str, dict]) -> int:
    serialized_lines = [
        json.dumps(records_by_company[key], sort_keys=True)
        for key in sorted(records_by_company, key=lambda item: records_by_company[item].get("company_name", ""))
    ]
    text = "\n".join(serialized_lines)
    if text:
        text += "\n"
    atomic_write(path, text)
    return len(serialized_lines)


def load_non_greenhouse_companies(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    companies_by_key: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        company_name = canonical_company_name(line)
        if not company_name:
            continue
        companies_by_key[company_cache_key(company_name)] = company_name
    return companies_by_key


def save_non_greenhouse_companies(path: Path, companies_by_key: dict[str, str]) -> int:
    company_names = [companies_by_key[key] for key in sorted(companies_by_key, key=lambda item: companies_by_key[item].lower())]
    text = "\n".join(company_names)
    if text:
        text += "\n"
    atomic_write(path, text)
    return len(company_names)
