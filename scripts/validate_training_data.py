#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


EXPECTED_ROLES = ["system", "user", "assistant"]


def validate_example(obj: dict, line_no: int) -> None:
    if "messages" not in obj or not isinstance(obj["messages"], list):
        raise ValueError(f"Line {line_no}: missing messages array.")
    messages = obj["messages"]
    if len(messages) != 3:
        raise ValueError(f"Line {line_no}: expected exactly 3 messages.")
    roles = [message.get("role") for message in messages]
    if roles != EXPECTED_ROLES:
        raise ValueError(f"Line {line_no}: expected roles {EXPECTED_ROLES}, got {roles}.")
    for idx, message in enumerate(messages, 1):
        if not isinstance(message.get("content"), str) or not message["content"].strip():
            raise ValueError(f"Line {line_no}: message {idx} has empty content.")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/validate_training_data.py training_data/application_writing_training.jsonl")
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        return 2

    count = 0
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"Line {line_no}: invalid JSON: {exc}")
                return 1
            try:
                validate_example(obj, line_no)
            except ValueError as exc:
                print(str(exc))
                return 1
            count += 1

    if count < 100:
        print(f"Validation failed: expected at least 100 examples, found {count}.")
        return 1

    print(f"Validation passed: {count} examples.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
