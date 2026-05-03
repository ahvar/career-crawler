from __future__ import annotations

import re
from typing import Iterable

from .common import clean_display_text, company_cache_key, dedupe_preserve_order
from .models import TargetCompany


def build_slug_candidates(company_name: str, *, greenhouse_slug_hints: dict[str, tuple[str, ...]]) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", company_name.lower())
    if not tokens:
        return []

    hinted = list(greenhouse_slug_hints.get(company_name, ()))
    generated = [
        "".join(tokens),
        "-".join(tokens),
        "_".join(tokens),
    ]
    if len(tokens) > 1:
        generated.extend(
            [
                tokens[0],
                f"{tokens[0]}{tokens[-1]}",
                f"{tokens[0]}-{tokens[-1]}",
            ]
        )

    cleaned_candidates: list[str] = []
    for candidate in hinted + generated:
        cleaned = candidate.strip("-_")
        if cleaned:
            cleaned_candidates.append(cleaned)
    return dedupe_preserve_order(cleaned_candidates)


def build_target_companies(
    company_names: Iterable[str],
    *,
    greenhouse_slug_hints: dict[str, tuple[str, ...]],
) -> list[TargetCompany]:
    targets: list[TargetCompany] = []
    seen_company_keys: set[str] = set()
    for company_name in company_names:
        company_name = clean_display_text(company_name)
        if not company_name:
            continue
        company_key = company_cache_key(company_name)
        if company_key in seen_company_keys:
            continue
        seen_company_keys.add(company_key)
        targets.append(
            TargetCompany(
                name=company_name,
                slug_candidates=tuple(build_slug_candidates(company_name, greenhouse_slug_hints=greenhouse_slug_hints)),
            )
        )
    return targets