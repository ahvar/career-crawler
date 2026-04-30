# Gregslist Company Name Crawl Plan

## Purpose

Use Gregslist as a supplementary source of Austin company names when manual collection from Built In is incomplete or needs cross-checking.

## Source And Policy

- Source listing: `https://gregslist.com/austin/search/?filtered=true`
- `robots.txt` currently has an empty `Disallow:` for `User-agent: *`
- `robots.txt` specifies `Crawl-delay: 10`
- The implementation must wait at least 10 seconds between requests

## Scope

- Collect company names only
- Do not crawl company detail pages unless this plan is expanded later
- Do not enrich with jobs, categories, descriptions, or other metadata in the first pass
- Use Gregslist as supplementary data, not the primary source of record

## Expected Listing Behavior

- The Austin company listings appear in static HTML
- Pagination is exposed through query parameters like `paged=2`, `paged=3`, and so on
- Browser automation should not be necessary if the current HTML structure remains stable

## Implementation Steps

1. Create a small standalone script, for example `scripts/crawl_gregslist_company_names.py`.
2. Fetch the Austin search listing URL with a clear custom user agent.
3. Parse one page of HTML and identify the selectors that contain visible company names.
4. Extract the company names from listing cards only.
5. Follow the paginated listing URLs one page at a time.
6. Sleep for at least 10 seconds between every HTTP request.
7. Deduplicate names across pages while preserving first-seen order.
8. Stop when the next page does not exist, returns no company cards, or produces no new names.
9. Write the final output as a newline-delimited text file.
10. Keep the script focused on name extraction so it is easy to audit and rerun.

## Suggested Output

- Default output path: `gregslist_austin_company_names.txt`
- Optional future output: CSV with `company_name` and `source_page_url`

## Validation Steps

1. Run the script against page 1 only and confirm names are extracted correctly.
2. Run pages 1 and 2 and confirm pagination and deduplication work.
3. Verify the request timestamps show at least 10 seconds between requests.
4. Compare the final deduplicated count against the approximate listing count shown on Gregslist.
5. Spot check a handful of extracted names against the live page.

## Failure Handling

- If selectors break, inspect one saved HTML page and update the parser locally.
- If rate limiting or blocking appears, stop the crawl and reassess before retrying.
- If Gregslist changes `robots.txt`, re-check policy before the next run.

## Non-Goals

- No company profile enrichment
- No job scraping
- No merging into the Greenhouse crawler until the standalone extractor is proven

## Integration Later

If the standalone script proves reliable, integrate it later by:

1. Adding a CLI entrypoint or flag consistent with existing repo scripts.
2. Writing output into a clearly named supplemental source file.
3. Keeping Built In as the manually curated primary list and using Gregslist for backfill and comparison.