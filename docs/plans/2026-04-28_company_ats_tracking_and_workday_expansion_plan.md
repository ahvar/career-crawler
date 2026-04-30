# Company ATS Tracking And Workday Expansion Plan

## Status Update (2026-04-29)

This plan is now mostly complete. The remaining work is no longer broad Workday discovery; it is code cleanup plus more targeted ATS strategies.

Current live state:

- `281` ATS registry records
- `9` confirmed Workday companies
- `90` companies still queued for `check_workday`
- `100` companies in the explicit `check_other_ats` backlog
- `125` matched jobs in the live snapshot

Completed outcomes that still matter:

- `crawler_cache/company_registry.jsonl` is now the canonical ATS registry.
- The ATS report and queue-driven Workday discovery flow exist and are working.
- Clean `not_found` Workday results can now be applied separately into `check_other_ats`.
- Legal-entity normalization and targeted `--company` discovery were fixed.
- Confirmed legal-name validations now include `Chevron` and `DuPont`, and alias coverage has started for confirmed legal-entity names.

## Technical Debt

1. `crawl_greenhouse.py` still owns too many thin wrappers and mutation paths.
  The file wraps many `ats.storage` functions one-for-one and still contains direct workflow mutation helpers such as `promote_company_to_workday` and `record_missing_workday_board`. Those should move into a dedicated mutation/service module so the CLI entrypoint stops owning state transitions.

2. Workday mutation logic is duplicated.
  `record_missing_workday_board` and `promote_company_to_workday` both load and rewrite revisit records plus ATS registry records with overlapping field logic. That should become one shared update path with status-specific parameters.

3. The repo has repeated JSON/JSONL helper code.
  `scripts/application_materials_pipeline.py` and `scripts/build_training_data.py` both define local `load_json` and `load_jsonl` helpers even though `ats/storage.py` already centralizes similar persistence helpers.

4. Active docs were drifting and duplicating each other.
  `README.md`, `agents.md`, and this plan were all carrying overlapping workflow details. `README.md` should stay user-facing and operational, while plan documents should stay short and only cover current decisions and next steps.

## Next Strategy

The next ATS strategy should favor targeted single-company extraction paths over brute-force Workday guessing.

For Adobe specifically, the search-results page already exposes enough structured data to support a dedicated extractor:

- the page source includes `phApp.ddo.eagerLoadRefineSearch.data.jobs`
- that payload already contains job titles, job ids, locations, categories, `applyUrl`, and teaser text
- pagination appears to be controlled by the `from` query parameter with a page size of `10`
- job detail URLs follow `/us/en/job/{jobId}/{slug}`

That means Adobe-like Phenom People sites can likely be crawled by:

1. detecting the embedded `phApp` / `eagerLoadRefineSearch` payload
2. iterating `from=0,10,20,...` until `from >= totalHits`
3. filtering titles from the embedded listing payload first
4. fetching detail pages only for matched jobs to collect full descriptions

## Active Next Steps

1. Prototype a single-company extractor for Adobe-style Phenom People listing pages.
2. Refactor Workday mutation logic out of `crawl_greenhouse.py` into a shared ATS workflow module.
3. Continue targeted alias validation for externally supplied legal-entity names only when a board is already confirmed or strongly indicated.
4. Keep the remaining 90-company Workday queue deferred until the targeted extractor path is evaluated.