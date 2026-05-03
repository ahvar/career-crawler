from __future__ import annotations

from typing import Any


def score_evidence(item: dict[str, Any], job: Any) -> int:
    score = 0
    if job.role_family in item.get("role_tags", []):
        score += 5
    for skill in job.skill_tags:
        if skill in item.get("skill_tags", []):
            score += 3
    if item.get("strength") == "strong":
        score += 2
    if item.get("is_quantified"):
        score += 1
    if job.role_family == "bioinformatics" and "genomics" in item.get("domain_tags", []):
        score += 3
    if job.role_family == "data_engineering" and any(
        tag in item.get("skill_tags", []) for tag in ["sql", "python", "aws"]
    ):
        score += 2
    if job.role_family == "technical_support":
        if "technical_support" in item.get("role_tags", []):
            score += 6
        if any(
            tag in item.get("skill_tags", [])
            for tag in ["support", "troubleshooting", "writing"]
        ):
            score += 4
        item_text = item.get("text", "").lower()
        if "technical support" in item_text or "root cause" in item_text:
            score += 4
    if job.role_family == "solutions_engineering":
        if "solutions_engineering" in item.get("role_tags", []) or "customer_success" in item.get(
            "role_tags", []
        ):
            score += 4
        if any(tag in item.get("skill_tags", []) for tag in ["writing", "support"]):
            score += 2
    return score


def select_evidence(
    evidence_bank: list[dict[str, Any]],
    job: Any,
    limit: int = 8,
) -> list[dict[str, Any]]:
    ranked = sorted(
        evidence_bank,
        key=lambda item: (
            score_evidence(item, job),
            item.get("strength") == "strong",
            item["evidence_id"],
        ),
        reverse=True,
    )
    chosen = []
    seen = set()
    for item in ranked:
        if score_evidence(item, job) <= 0:
            continue
        key = (item.get("organization_or_project"), item.get("normalized_summary"))
        if key in seen:
            continue
        chosen.append(item)
        seen.add(key)
        if len(chosen) >= limit:
            break
    return chosen