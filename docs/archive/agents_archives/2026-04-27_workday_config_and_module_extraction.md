# Workday Config And Module Extraction (2026-04-27)

## Scope Closed

This note archives the completed cleanup work that followed the initial Workday prototype validation.

## Completed Outcomes

- ATS-specific crawler code is now split into dedicated modules:
  - `ats_models.py`
  - `ats_common.py`
  - `ats_greenhouse.py`
  - `ats_workday.py`
- Shared hint/config loading was centralized in `ats_config.py`.
- Greenhouse slug hints now live in `greenhouse_slug_hints.json`.
- Workday tenant hints now live in `workday_board_hints.json`.
- The crawler now falls back from Greenhouse into configured Workday tenants when Greenhouse does not return current matches for those companies.

## Validated Workday Tenants

- Red Hat
- Silicon Labs
- 3M
- Amgen

## Validated Behavior

- Workday listings fetch works through `/wday/cxs/{tenant}/{site}/jobs` for the configured tenants.
- Workday detail fetching extracts job descriptions from JSON-LD `JobPosting` with Open Graph fallback.
- Workday public detail fetching retries a `/details/<job-slug>` route when the `externalPath`-derived route fails.
- Greenhouse slug hints still resolve through the shared config path.

## Validation Results Captured During This Slice

- Red Hat: 339 jobs scanned, 37 matches.
- Silicon Labs: 64 jobs scanned, 0 Austin/US-remote matches.
- 3M: 581 jobs scanned, 11 matches.
- Amgen: 1309 jobs scanned, 3 matches.

## Related Files

- `crawl_greenhouse.py`
- `ats_common.py`
- `ats_config.py`
- `ats_greenhouse.py`
- `ats_models.py`
- `ats_workday.py`
- `greenhouse_slug_hints.json`
- `workday_board_hints.json`
- `docs/reference/workday_api.md`
