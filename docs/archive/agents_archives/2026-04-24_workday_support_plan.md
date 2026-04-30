# 2026-04-24 Workday Support Plan

## Goal

Extend the current company-discovery workflow so a company can be evaluated first for Greenhouse and, if no Greenhouse board is found, then for Workday. The end state should support identifying Workday-hosted job boards, fetching jobs through the Workday API, and reusing the existing title/location matching and workflow overlays.

## Red Hat Pilot Conclusion

Red Hat is now the concrete reference example for the first Workday implementation slice.

- Board page: `https://redhat.wd5.myworkdayjobs.com/en-US/jobs/jobs`
- Example detail page: `https://redhat.wd5.myworkdayjobs.com/en-US/jobs/jobs/details/Software-Engineer_R-056095-1`
- Listings API: `POST https://redhat.wd5.myworkdayjobs.com/wday/cxs/redhat/jobs/jobs`

Validated on 2026-04-27:

- A minimal JSON POST returned listings successfully with no browser automation and no cookie requirement for the initial request.
- The jobs-page HTML is a JavaScript bootstrap shell that loads the Workday frontend bundle; it is not the primary data source for listings.
- The crawler should therefore target the JSON API directly instead of trying to reverse-engineer browser click behavior.
- The API response includes `jobPostings`, `total`, and `facets`, which is enough to support a first-pass integration.

## Working Assumptions

- Greenhouse remains the first ATS check because its board discovery path is cheap and already implemented.
- Workday often serves JavaScript-rendered job pages, but job listings are typically backed by a JSON API.
- Workday discovery is less uniform than Greenhouse slug discovery because it usually requires both a Workday host and a site name before the API endpoint can be derived.
- The current crawler already has the right downstream structures for workflow state: `crawler_cache/careers_scraped.jsonl`, `crawler_cache/non_greenhouse_companies.txt`, `crawler_cache/company_revisit.jsonl`, and `crawler_cache/matched_jobs.jsonl`.
- The current code shape in `crawl_greenhouse.py` is still Greenhouse-centric, especially `CompanyAssessment`, `build_search_record`, and the `source: "greenhouse"` cache record assumption, so Workday support should start by loosening those seams rather than with a large architectural rewrite.

## Research Questions To Resolve Early

1. Can a target company's Workday board be discovered heuristically from company-name variants often enough to automate a useful first pass?
2. For companies where heuristic discovery fails, what manual hint surface is needed to keep the workflow practical?
3. Which public URL format should be treated as canonical when Workday exposes both `externalPath`-style routes and `/details/` routes?
4. Which detail endpoint should be used to fetch full job descriptions after the listings page identifies a candidate job?
5. What minimum normalized fields are needed so Greenhouse and Workday jobs can share the same title-family and location filters?

## Proposed Implementation Steps

1. Generalize the narrowest shared metadata first.
Expand `CompanyAssessment` and search-cache records so they can represent `greenhouse`, `workday`, and unresolved companies. This should include ATS type, board URL, board identifier, and optionally a derived API URL.

2. Split Greenhouse assumptions out of search-record writing.
Refactor `build_search_record` so `source` is no longer hardcoded to `greenhouse`, and make sure a future Workday path can store `resolved_slug`-equivalent identifiers without pretending they are Greenhouse slugs.

3. Add a small Workday board resolver.
Start with explicit Red Hat-style parsing rules:
	- detect a Workday board URL
	- extract tenant from the hostname or bootstrap config
	- extract site ID from the path or bootstrap config
	- derive the listings API URL

4. Promote the listings API prototype into reusable production code.
Move the fetch logic from `test_workday_api.py` into crawler code that supports pagination through `offset` and `limit`. Keep the first pass focused on unfiltered listing retrieval with empty `appliedFacets`.

5. Add Workday job normalization.
Create a normalization step that maps Workday fields such as `title`, `externalPath`, `locationsText`, `remoteType`, `postedOn`, and `bulletFields` into the shared matching pipeline.

6. Resolve the public URL strategy before persisting jobs.
Red Hat shows that API `externalPath` values and `/details/` routes can both resolve. Choose one canonical persisted format or add a normalization rule that converts API paths into the preferred public detail URL.

7. Add Workday detail fetching only after listings work.
Do not block the first integration on full job-description fetching. First prove we can discover the board, list jobs, and identify likely matches. Then add a second step for fetching full descriptions for only matched roles.

8. Keep manual hints explicit and small.
Add a hint table for companies whose Workday tenant name, site ID, or careers URL cannot be derived heuristically. This is the likely escape hatch for real-world exceptions.

9. Pilot on Red Hat before broad ATS research.
Treat Red Hat as the first end-to-end validation target: detect board, derive API, paginate listings, normalize records, and produce a candidate match list without affecting the Greenhouse path.

10. Expand to a small non-Greenhouse subset.
After the Red Hat pilot works, pick a few entries from `crawler_cache/company_revisit.jsonl` that are likely Workday users and test the same flow.

11. Reassess larger abstraction work after the pilot.
Only after the pilot succeeds should the repo decide whether it needs a provider abstraction, a renamed crawler entrypoint, or a broader ATS framework.

## Recommended Execution Order

1. Loosen `CompanyAssessment` and cache-record metadata so Workday can be represented cleanly.
2. Implement Red Hat board parsing and listings API derivation.
3. Integrate paginated Workday listings fetches.
4. Normalize Workday postings into the existing title-family matching flow.
5. Decide and implement canonical public Workday job URLs.
6. Add matched-job detail fetches for full descriptions.
7. Pilot Red Hat end to end.
8. Expand to a small non-Greenhouse subset.
9. Decide whether broader provider abstractions are still justified.

## Immediate Follow-Up Work

- Update the Red Hat example notes in `docs/reference/workday_api.md` whenever we validate a detail-description endpoint or canonical public URL rule.
- Implement the smallest production slice against Red Hat first instead of attempting general Workday discovery and full ATS abstraction in one step.
- Keep Workday support out of the application-material generation path until the crawler side can reliably produce normalized matched jobs and full descriptions.