from __future__ import annotations

from typing import Any

from training_data_evidence import select_evidence
from training_data_rendering import (
    build_cover_letter,
    build_resume_output,
    build_system_prompt,
    build_user_message,
    cover_letter_variants_for_job,
    resume_variants_for_job,
)


def build_training_examples(
    canonical_profile: dict[str, Any],
    evidence_bank: list[dict[str, Any]],
    jobs: list[Any],
) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for job in jobs:
        relevant_evidence = select_evidence(evidence_bank, job)
        for variant in cover_letter_variants_for_job(job):
            messages = [
                {"role": "system", "content": build_system_prompt("cover_letter")},
                {
                    "role": "user",
                    "content": build_user_message(
                        job,
                        canonical_profile,
                        relevant_evidence,
                        "cover_letter",
                        variant,
                    ),
                },
                {
                    "role": "assistant",
                    "content": build_cover_letter(job, relevant_evidence, variant),
                },
            ]
            examples.append({"messages": messages})
        for variant in resume_variants_for_job(job):
            messages = [
                {"role": "system", "content": build_system_prompt("resume")},
                {
                    "role": "user",
                    "content": build_user_message(
                        job,
                        canonical_profile,
                        relevant_evidence,
                        "resume",
                        variant,
                    ),
                },
                {
                    "role": "assistant",
                    "content": build_resume_output(job, relevant_evidence, variant),
                },
            ]
            examples.append({"messages": messages})
    return examples