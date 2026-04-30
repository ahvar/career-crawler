# Phase 3.5: Enhanced Job Crawler with Caching & Job Title Matching

**Status:** ✅ COMPLETED  
**Completion Date:** April 2026  
**Outputs:**
- `crawl_gregslist.py` - Polite asynchronous crawler with persistent cache support
- `README.md` - Updated crawler usage and cache documentation
- `crawler_cache/no_careers_page.txt` - Cache of company sites with no careers page found
- `crawler_cache/careers_scraped.jsonl` - Cache of scraped careers pages with re-scrape dates
- `crawler_cache/matched_jobs.jsonl` - Append-only matched job log

---

## Purpose
Before building the inference pipeline, the Gregslist crawler was upgraded into a stateful, cache-aware system that:

1. Avoids re-checking company websites known to have no careers page
2. Tracks when careers pages were last scraped and when they should be re-scraped
3. Searches careers pages for target job titles
4. Persists crawler state across runs

This phase reduced redundant crawling and made the job-discovery step more useful for later matching and application-generation work.

---

## Completed Capabilities

### 1. Target job title and role-family matching
Implemented role-family-based keyword coverage for:
- software engineering
- bioinformatics software engineering
- technical account management and customer-facing technical roles
- technical support and customer service
- adjacent technical roles

Matching behavior includes:
- case-insensitive matching
- partial phrase matching
- exclusion filtering for obviously sales-oriented roles
- structured-link-first matching, with fallback to text-block matching

### 2. Persistent no-careers cache
Implemented `crawler_cache/no_careers_page.txt` with:
- normalized homepage URLs
- optional `# CompanyName` comments for readability
- graceful malformed-line handling
- atomic rewrite behavior after crawl completion

### 3. Scraped careers-page cache
Implemented `crawler_cache/careers_scraped.jsonl` with:
- `url`
- `company_name`
- `last_scraped`
- `next_scrape`
- `careers_status`
- `matched_titles`
- `website_url`
- `scrape_count`

Behavior includes:
- 30-day default re-scrape interval
- skip when `next_scrape` is not due
- update and rewrite cache after crawl completion
- sort by `next_scrape` for easier inspection

### 4. Matched job persistence
Implemented `crawler_cache/matched_jobs.jsonl` as an append-only JSONL log of:
- company name
- careers page URL
- matched job title
- job URL
- matched keywords
- found date

### 5. Crawler workflow integration
Updated `crawl_gregslist.py` so the workflow now:
1. Loads cache files
2. Fetches Gregslist company profile pages
3. Extracts company websites
4. Skips cached no-careers websites
5. Skips scraped websites that are not due for re-scrape
6. Checks remaining websites and careers pages politely
7. Stores new cache outcomes
8. Logs matched jobs when found

### 6. CLI controls
Added:
- `--clear-cache`
- `--ignore-cache`
- `--show-cache-stats`
- `--rescrape-interval DAYS`

### 7. Verification completed
Verified locally with:
- Python syntax compilation
- CLI help output
- cache create/clear/show paths
- one live crawl run against Gregslist
- second live run confirming cache-hit skip behavior

One verified cache example from the live run:
- `11trees.com` was classified as `Not Found`
- it was written to `crawler_cache/no_careers_page.txt`
- the next run skipped it without re-fetching the company homepage

---

## Notes for Future Phases

- The crawler remains intentionally polite and shallow.
- Cache keys are normalized so `http` to `https` redirects do not break skip behavior.
- `matched_jobs.jsonl` is the bridge artifact most relevant for later inference-pipeline work.
- Future inference work can consume crawler outputs without having to rediscover jobs from scratch on every run.
