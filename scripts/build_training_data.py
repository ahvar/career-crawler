#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from training_data_examples import build_training_examples
from training_data_io import load_json, load_jsonl, write_jsonl
from training_data_jobs import JobDescription, load_job_descriptions


ROOT = Path(__file__).resolve().parents[1]
DERIVED_DIR = ROOT / "derived_profile"
JOB_DESCRIPTION_DIRS = [
    DERIVED_DIR / "job_descriptions",
    ROOT / "application_materials" / "job_descriptions",
]
TRAINING_DIR = ROOT / "training_data"
OUTPUT_PATH = TRAINING_DIR / "application_writing_training.jsonl"
BASE_MODEL = "gpt-4o-mini-2024-07-18"


def main() -> None:
    canonical_profile = load_json(DERIVED_DIR / "canonical_profile.json")
    evidence_bank = load_jsonl(DERIVED_DIR / "evidence_bank.jsonl")
    jobs = load_job_descriptions(root=ROOT, job_description_dirs=JOB_DESCRIPTION_DIRS)
    TRAINING_DIR.mkdir(exist_ok=True)
    examples = build_training_examples(canonical_profile, evidence_bank, jobs)
    write_jsonl(OUTPUT_PATH, examples)
    print(f"Wrote {len(examples)} training examples to {OUTPUT_PATH}")
    print(f"Base model target: {BASE_MODEL}")


if __name__ == "__main__":
    main()
