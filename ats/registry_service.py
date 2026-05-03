from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .models import CompanyAssessment
from .registry import (
    build_company_registry_records,
    categorize_company_registry_records,
    load_company_names_from_text_file,
)


@dataclass(frozen=True)
class RegistryServiceContext:
    default_company_names: tuple[str, ...]
    new_companies_path: Path
    workday_board_hints: dict[str, dict]
    load_company_search_cache: Callable[[], dict[str, dict]]
    load_non_greenhouse_companies: Callable[[], dict[str, str]]
    load_company_revisit_records: Callable[[], dict[str, dict]]
    load_company_registry_records: Callable[[], dict[str, dict]]
    save_company_registry_records: Callable[[dict[str, dict]], int]
    render_company_ats_report: Callable[[dict[str, dict], dict[str, list[dict]]], str]
    render_intake_workday_report: Callable[[dict[str, dict], list[str], Path], str]


def build_current_company_registry_records(
    context: RegistryServiceContext,
    *,
    search_cache: dict[str, dict] | None = None,
    non_greenhouse_cache: dict[str, str] | None = None,
    company_revisits: dict[str, dict] | None = None,
    existing_records: dict[str, dict] | None = None,
    greenhouse_assessments: Iterable[CompanyAssessment] = (),
    workday_assessments: Iterable[CompanyAssessment] = (),
    other_ats_assessments: Iterable[CompanyAssessment] = (),
) -> dict[str, dict]:
    return build_company_registry_records(
        search_records=search_cache if search_cache is not None else context.load_company_search_cache(),
        non_greenhouse_records=non_greenhouse_cache if non_greenhouse_cache is not None else context.load_non_greenhouse_companies(),
        revisit_records=company_revisits if company_revisits is not None else context.load_company_revisit_records(),
        registry_records=existing_records if existing_records is not None else context.load_company_registry_records(),
        default_company_names=context.default_company_names,
        workday_board_hints=context.workday_board_hints,
        greenhouse_assessments=greenhouse_assessments,
        workday_assessments=workday_assessments,
        other_ats_assessments=other_ats_assessments,
    )


def sync_company_registry(
    context: RegistryServiceContext,
    *,
    search_cache: dict[str, dict] | None = None,
    non_greenhouse_cache: dict[str, str] | None = None,
    company_revisits: dict[str, dict] | None = None,
    greenhouse_assessments: Iterable[CompanyAssessment] = (),
    workday_assessments: Iterable[CompanyAssessment] = (),
    other_ats_assessments: Iterable[CompanyAssessment] = (),
) -> int:
    records = build_current_company_registry_records(
        context,
        search_cache=search_cache,
        non_greenhouse_cache=non_greenhouse_cache,
        company_revisits=company_revisits,
        greenhouse_assessments=greenhouse_assessments,
        workday_assessments=workday_assessments,
        other_ats_assessments=other_ats_assessments,
    )
    return context.save_company_registry_records(records)


def format_company_ats_report(context: RegistryServiceContext) -> str:
    records = build_current_company_registry_records(context)
    categories = categorize_company_registry_records(records)
    return context.render_company_ats_report(records, categories)


def format_intake_workday_report(
    context: RegistryServiceContext,
    path: Path | None = None,
) -> str:
    report_path = path or context.new_companies_path
    records = build_current_company_registry_records(context)
    company_names = load_company_names_from_text_file(report_path)
    return context.render_intake_workday_report(records, company_names, report_path)