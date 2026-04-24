"""Fine-tuning training data upload script.

This script uploads JSONL training data to OpenAI and starts a fine-tuning job
based on ``gpt-4o-mini-2024-07-18``.

Workflow:
1. Run this script to upload training data and start fine-tuning.
2. Monitor the job until completion.
3. Copy the resulting fine-tuned model ID into your runtime configuration.

Usage:
    export OPENAI_API_KEY=...
    python upload_training_data.py --file training_data/application_writing_training.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from openai import OpenAI

from config import Config


def upload_training_file(client: OpenAI, file_path: Path) -> str:
    """Upload the JSONL file used for fine-tuning and return the file id."""
    with file_path.open("rb") as training_file:
        uploaded_file = client.files.create(file=training_file, purpose="fine-tune")

    print(f"File uploaded successfully: {uploaded_file.id}")
    return uploaded_file.id


def create_fine_tuning_job(client: OpenAI, file_id: str, model: str) -> str:
    """Create a fine-tuning job and return the job id."""
    job = client.fine_tuning.jobs.create(training_file=file_id, model=model)

    print(f"Fine-tuning job created successfully: {job.id}")
    print("Monitor this job in the OpenAI dashboard:")
    print(f"https://platform.openai.com/finetune/{job.id}?filter=all")
    return job.id


def validate_training_data(training_data_filepath: Path) -> Path:
    if training_data_filepath is None:
        raise ValueError("No file path provided.")
    if not training_data_filepath.exists():
        raise ValueError(f"File not found: {training_data_filepath}")
    try:
        with training_data_filepath.open("r", encoding="utf-8") as f:
            example_count = 0
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception as e:
                    raise ValueError(f"Invalid JSON on line {i}: {e}")
                messages = payload.get("messages")
                if not isinstance(messages, list) or len(messages) != 3:
                    raise ValueError(f"Line {i}: expected a 3-message chat example.")
                roles = [message.get("role") for message in messages]
                if roles != ["system", "user", "assistant"]:
                    raise ValueError(
                        f"Line {i}: expected roles ['system', 'user', 'assistant'], got {roles}."
                    )
                for message in messages:
                    content = message.get("content")
                    if not isinstance(content, str) or not content.strip():
                        raise ValueError(f"Line {i}: all message contents must be non-empty strings.")
                example_count += 1
    except Exception as e:
        raise ValueError(f"Error reading file: {e}")
    if example_count < 100:
        raise ValueError(f"Expected at least 100 examples, found {example_count}.")
    return training_data_filepath


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload fine-tuning data and create an OpenAI fine-tuning job.")
    parser.add_argument(
        "--file",
        type=Path,
        default=Path(Config.DEFAULT_JSONL_PATH),
        help=f"Path to JSONL training file (default: {Config.DEFAULT_JSONL_PATH})",
    )
    parser.add_argument(
        "--model",
        default=Config.BASE_MODEL,
        help=(
            f"Base model for fine-tuning (default: {Config.BASE_MODEL}). "
            "After fine-tuning, update OPENAI_FINETUNED_MODEL for inference."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Upload training data and start a fine-tuning job."""
    args = parse_args()
    try:
        file = validate_training_data(args.file)
    except ValueError as exc:
        print(exc)
        raise SystemExit(2)

    api_key = Config.OPENAI_API_KEY
    if not api_key:
        print("Please set OPENAI_API_KEY environment variable")
        raise SystemExit(1)
    if OpenAI is None:
        print("Missing dependency: openai. Install it in the environment before uploading training data.")
        raise SystemExit(1)

    client = OpenAI(api_key=api_key)
    file_id = upload_training_file(client, file)
    create_fine_tuning_job(client, file_id=file_id, model=args.model)


if __name__ == "__main__":
    main()
