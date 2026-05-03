from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .commands import CommandContext
from .config import (
    WORKDAY_BOARD_HINTS_PATH,
    load_greenhouse_slug_hints,
    load_phenom_search_hints,
    load_workday_board_hints,
)
from .registry_service import RegistryServiceContext
from .runtime_state import RuntimeState
from .tracking_service import TrackingServiceContext


DEFAULT_DELAY_SECONDS = 0.4
DEFAULT_CONCURRENCY = 4
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_NON_GREENHOUSE_REVISIT_DAYS = 30
DEFAULT_WORKDAY_DISCOVERY_LIMIT = 10
VALID_JOB_TRACKING_STATUSES = ("pending_review", "applied", "revisit_later", "not_a_fit", "archived")


@dataclass(frozen=True)
class CrawlBootstrap:
    cache_dir: Path
    archive_dir: Path
    matched_jobs_path: Path
    searched_companies_path: Path
    non_greenhouse_companies_path: Path
    job_tracking_path: Path
    company_revisit_path: Path
    company_registry_path: Path
    new_companies_path: Path
    workday_board_hints_path: Path
    default_target_companies: tuple[str, ...]
    greenhouse_slug_hints: dict[str, tuple[str, ...]]
    workday_board_hints: dict[str, dict]
    phenom_search_hints: dict[str, dict]
    default_delay_seconds: float = DEFAULT_DELAY_SECONDS
    default_concurrency: int = DEFAULT_CONCURRENCY
    default_timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    default_non_greenhouse_revisit_days: int = DEFAULT_NON_GREENHOUSE_REVISIT_DAYS
    default_workday_discovery_limit: int = DEFAULT_WORKDAY_DISCOVERY_LIMIT
    valid_job_tracking_statuses: tuple[str, ...] = VALID_JOB_TRACKING_STATUSES

    @property
    def runtime_state(self) -> RuntimeState:
        return RuntimeState(
            cache_dir=self.cache_dir,
            archive_dir=self.archive_dir,
            matched_jobs_path=self.matched_jobs_path,
            searched_companies_path=self.searched_companies_path,
            non_greenhouse_companies_path=self.non_greenhouse_companies_path,
            job_tracking_path=self.job_tracking_path,
            company_revisit_path=self.company_revisit_path,
            company_registry_path=self.company_registry_path,
        )

    def make_registry_service_context(self, *, render_company_ats_report, render_intake_workday_report) -> RegistryServiceContext:
        runtime_state = self.runtime_state
        return RegistryServiceContext(
            default_company_names=self.default_target_companies,
            new_companies_path=self.new_companies_path,
            workday_board_hints=self.workday_board_hints,
            load_company_search_cache=runtime_state.load_company_search_cache,
            load_non_greenhouse_companies=runtime_state.load_non_greenhouse_companies,
            load_company_revisit_records=runtime_state.load_company_revisit_records,
            load_company_registry_records=runtime_state.load_company_registry_records,
            save_company_registry_records=runtime_state.save_company_registry_records,
            render_company_ats_report=render_company_ats_report,
            render_intake_workday_report=render_intake_workday_report,
        )

    def make_tracking_service_context(self, *, render_tracking_report) -> TrackingServiceContext:
        runtime_state = self.runtime_state
        return TrackingServiceContext(
            matched_jobs_path=self.matched_jobs_path,
            load_job_tracking_records=runtime_state.load_job_tracking_records,
            load_company_revisit_records=runtime_state.load_company_revisit_records,
            render_tracking_report=render_tracking_report,
        )

    def make_command_context(
        self,
        *,
        crawl_error_type: type[Exception],
        format_tracking_report,
        format_company_ats_report,
        format_intake_workday_report,
        format_workday_discovery_report,
        sync_company_registry,
        sync_non_greenhouse_company_revisits,
        upsert_job_tracking_record,
        backfill_pending_review_records,
        backfill_workday_snapshot_details,
    ) -> CommandContext:
        runtime_state = self.runtime_state
        return CommandContext(
            matched_jobs_path=self.matched_jobs_path,
            company_revisit_path=self.company_revisit_path,
            workday_board_hints_path=self.workday_board_hints_path,
            new_companies_path=self.new_companies_path,
            default_company_names=self.default_target_companies,
            default_non_greenhouse_revisit_days=self.default_non_greenhouse_revisit_days,
            valid_job_tracking_statuses=self.valid_job_tracking_statuses,
            workday_board_hints=self.workday_board_hints,
            crawl_error_type=crawl_error_type,
            summarize_output_stats=runtime_state.summarize_output_stats,
            format_tracking_report=format_tracking_report,
            format_company_ats_report=format_company_ats_report,
            format_intake_workday_report=format_intake_workday_report,
            format_workday_discovery_report=format_workday_discovery_report,
            load_company_search_cache=runtime_state.load_company_search_cache,
            load_non_greenhouse_companies=runtime_state.load_non_greenhouse_companies,
            load_company_revisit_records=runtime_state.load_company_revisit_records,
            save_company_revisit_records=runtime_state.save_company_revisit_records,
            load_company_registry_records=runtime_state.load_company_registry_records,
            save_company_registry_records=runtime_state.save_company_registry_records,
            load_job_tracking_records=runtime_state.load_job_tracking_records,
            save_job_tracking_records=runtime_state.save_job_tracking_records,
            sync_company_registry=sync_company_registry,
            sync_non_greenhouse_company_revisits=sync_non_greenhouse_company_revisits,
            upsert_job_tracking_record=upsert_job_tracking_record,
            backfill_pending_review_records=backfill_pending_review_records,
            backfill_workday_snapshot_details=backfill_workday_snapshot_details,
        )


DEFAULT_TARGET_COMPANIES = (
    "Affirm",
    "Striveworks",
    "Instacart",
    "Elastic",
    "Doximity",
    "Reddit",
    "Upside",
    "Expedia Group",
    "LogicMonitor",
    "PwC",
    "Vercel",
    "AlertMedia",
    "SciPlay",
    "Wise",
    "inKind",
    "Rubrik",
    "GroceryTV",
    "Rapid7",
    "Lansweeper",
    "CDW",
    "Optimal",
    "ARM",
    "Sysco LABS",
    "8am",
    "CrowdStrike",
    "ReUp Education",
    "Udemy",
    "ServiceNow",
    "CiscoThousandEyes",
    "Dealerware",
    "Imprivata",
    "Navan",
    "Apex Fintech Solutions",
    "BigCommerce",
    "Snap Inc.",
    "BAE Systems, Inc.",
    "Motive",
    "Riot Platforms, Inc.",
    "Closinglock",
    "CDW",
    "Imprivata",
    "Ericsson",
    "Atlassian",
    "UL Solutions",
    "Zello",
    "SEON",
    "VISA",
    "Spectrum",
    "2K",
    "MongoDB",
    "Upstart",
    "Dscout",
    "Invoice Home",
    "Snap! Mobile",
    "Aceable",
    "Metropolis Technologies",
    "CAIS",
    "Flatfile",
    "Dropbox",
    "Agora RE",
    "Huntress",
    "M-Files",
    "Moov",
    "Hudson River Trading",
    "Babylist",
    "Unchained",
    "Rev",
    "The Knot Worldwide",
    "Citylitics",
    "Airtable",
    "ConverseNow",
    "Sprinklr",
    "Origis Energy",
    "Arganteal Corporation",
    "All Options",
    "Orchard",
    "Pensa Systems",
    "Darktrace",
    "ActiveProspect",
    "Pattern Bioscience",
    "CoStar Group",
    "DevDocs",
    "GSD&M",
    "Peddle",
    "Avathon",
    "Gamurs Group",
    "Conduent",
    "SmartBiz Loans",
)


def build_default_bootstrap(*, clean_display_text, company_cache_key) -> CrawlBootstrap:
    cache_dir = Path("crawler_cache")
    return CrawlBootstrap(
        cache_dir=cache_dir,
        archive_dir=cache_dir / "archive",
        matched_jobs_path=cache_dir / "matched_jobs.jsonl",
        searched_companies_path=cache_dir / "careers_scraped.jsonl",
        non_greenhouse_companies_path=cache_dir / "non_greenhouse_companies.txt",
        job_tracking_path=cache_dir / "job_tracking.jsonl",
        company_revisit_path=cache_dir / "company_revisit.jsonl",
        company_registry_path=cache_dir / "company_registry.jsonl",
        new_companies_path=Path("new_companies.txt"),
        workday_board_hints_path=WORKDAY_BOARD_HINTS_PATH,
        default_target_companies=DEFAULT_TARGET_COMPANIES,
        greenhouse_slug_hints=load_greenhouse_slug_hints(normalize_text=clean_display_text),
        workday_board_hints=load_workday_board_hints(
            normalize_company_key=company_cache_key,
            normalize_text=clean_display_text,
        ),
        phenom_search_hints=load_phenom_search_hints(
            normalize_company_key=company_cache_key,
            normalize_text=clean_display_text,
        ),
    )