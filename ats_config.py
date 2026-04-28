from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


ROOT_DIR = Path(__file__).resolve().parent
GREENHOUSE_SLUG_HINTS_PATH = ROOT_DIR / "greenhouse_slug_hints.json"
WORKDAY_BOARD_HINTS_PATH = ROOT_DIR / "workday_board_hints.json"


def _load_json_object(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_greenhouse_slug_hints(*, normalize_text: Callable[[str], str]) -> dict[str, tuple[str, ...]]:
    payload = _load_json_object(GREENHOUSE_SLUG_HINTS_PATH)
    hints: dict[str, tuple[str, ...]] = {}
    for company_name, values in payload.items():
        if not isinstance(company_name, str) or not isinstance(values, list):
            continue
        normalized_values = tuple(
            candidate for candidate in (normalize_text(str(value)) for value in values) if candidate
        )
        if normalized_values:
            hints[normalize_text(company_name)] = normalized_values
    return hints


def load_workday_board_hints(
    *,
    normalize_company_key: Callable[[str], str],
    normalize_text: Callable[[str], str],
) -> dict[str, dict[str, str]]:
    payload = _load_json_object(WORKDAY_BOARD_HINTS_PATH)
    hints: dict[str, dict[str, str]] = {}
    for company_name, hint in payload.items():
        if not isinstance(hint, dict):
            continue
        normalized_company = normalize_company_key(str(company_name))
        tenant = normalize_text(str(hint.get("tenant") or ""))
        site_id = normalize_text(str(hint.get("site_id") or ""))
        board_url = normalize_text(str(hint.get("board_url") or ""))
        if not normalized_company or not tenant or not site_id or not board_url:
            continue
        hints[normalized_company] = {
            "tenant": tenant,
            "site_id": site_id,
            "board_url": board_url,
        }
    return hints