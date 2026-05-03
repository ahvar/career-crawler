from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .storage import (
    count_jsonl_rows,
    count_text_rows,
    load_company_registry_records as load_company_registry_records_from_path,
    load_company_revisit_records as load_company_revisit_records_from_path,
    load_company_search_cache as load_company_search_cache_from_path,
    load_job_tracking_records as load_job_tracking_records_from_path,
    load_non_greenhouse_companies as load_non_greenhouse_companies_from_path,
    save_company_registry_records as save_company_registry_records_to_path,
    save_company_revisit_records as save_company_revisit_records_to_path,
    save_company_search_cache as save_company_search_cache_to_path,
    save_job_tracking_records as save_job_tracking_records_to_path,
    save_non_greenhouse_companies as save_non_greenhouse_companies_to_path,
)


@dataclass(frozen=True)
class RuntimeState:
    cache_dir: Path
    archive_dir: Path
    matched_jobs_path: Path
    searched_companies_path: Path
    non_greenhouse_companies_path: Path
    job_tracking_path: Path
    company_revisit_path: Path
    company_registry_path: Path

    def ensure_cache_dir(self) -> None:
        self.cache_dir.mkdir(exist_ok=True)
        self.archive_dir.mkdir(exist_ok=True)

    def ensure_tracking_files(self) -> None:
        self.ensure_cache_dir()
        for path in (self.job_tracking_path, self.company_revisit_path, self.company_registry_path):
            if not path.exists():
                path.write_text("", encoding="utf-8")

    def summarize_output_stats(self) -> str:
        self.ensure_cache_dir()
        self.ensure_tracking_files()
        archived_match_files = sorted(self.archive_dir.glob("matched_jobs*.jsonl"))
        lines = [
            f"Output file: {self.matched_jobs_path}",
            f"Current matched jobs: {count_jsonl_rows(self.matched_jobs_path)}",
            f"Searched companies cache: {len(self.load_company_search_cache())}",
            f"Known non-Greenhouse companies: {count_text_rows(self.non_greenhouse_companies_path)}",
            f"Company ATS registry records: {count_jsonl_rows(self.company_registry_path)}",
            f"Tracked jobs: {count_jsonl_rows(self.job_tracking_path)}",
            f"Tracked company revisits: {count_jsonl_rows(self.company_revisit_path)}",
            f"Archived matched-job files: {len(archived_match_files)}",
        ]
        return "\n".join(lines)

    def load_job_tracking_records(self) -> dict[tuple[str, str], dict]:
        self.ensure_tracking_files()
        return load_job_tracking_records_from_path(self.job_tracking_path)

    def save_job_tracking_records(self, records: dict[tuple[str, str], dict]) -> int:
        return save_job_tracking_records_to_path(self.job_tracking_path, records)

    def load_company_revisit_records(self) -> dict[str, dict]:
        self.ensure_tracking_files()
        return load_company_revisit_records_from_path(self.company_revisit_path)

    def save_company_revisit_records(self, records: dict[str, dict]) -> int:
        return save_company_revisit_records_to_path(self.company_revisit_path, records)

    def load_company_registry_records(self) -> dict[str, dict]:
        self.ensure_tracking_files()
        return load_company_registry_records_from_path(self.company_registry_path)

    def save_company_registry_records(self, records: dict[str, dict]) -> int:
        return save_company_registry_records_to_path(self.company_registry_path, records)

    def load_company_search_cache(self) -> dict[str, dict]:
        return load_company_search_cache_from_path(self.searched_companies_path)

    def save_company_search_cache(self, records_by_company: dict[str, dict]) -> int:
        return save_company_search_cache_to_path(self.searched_companies_path, records_by_company)

    def load_non_greenhouse_companies(self) -> dict[str, str]:
        return load_non_greenhouse_companies_from_path(self.non_greenhouse_companies_path)

    def save_non_greenhouse_companies(self, companies_by_key: dict[str, str]) -> int:
        return save_non_greenhouse_companies_to_path(self.non_greenhouse_companies_path, companies_by_key)