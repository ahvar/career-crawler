from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TargetCompany:
    name: str
    slug_candidates: tuple[str, ...] = ()


@dataclass
class MatchedJob:
    company_name: str
    company_slug: str
    careers_url: str
    greenhouse_job_id: str
    job_title: str
    job_url: str
    job_location: str
    matched_keywords: list[str]
    matched_role_families: list[str]
    found_date: str
    job_description: str


@dataclass
class CompanyAssessment:
    name: str
    attempted_slugs: list[str]
    resolved_slug: str | None
    board_url: str | None
    status: str
    source: str = "greenhouse"
    jobs_seen: int = 0
    matched_jobs: list[MatchedJob] = field(default_factory=list)


@dataclass
class CrawlRun:
    assessments: list[CompanyAssessment]
    matched_jobs: list[MatchedJob]


@dataclass(frozen=True)
class JobMatchResult:
    matched_job: MatchedJob | None
    title_matched: bool = False
    location_matched: bool = False