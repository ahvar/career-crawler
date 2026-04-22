# Greenhouse Job Crawler

This project now uses a Greenhouse-only crawler that queries Greenhouse job boards directly instead of discovering companies through Gregslist.

The crawler:
- starts from a fixed list of target companies
- generates likely Greenhouse board slugs for each company
- probes `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs`
- fetches full job details for matching roles
- keeps only jobs located in `Austin, TX` or `Remote` roles explicitly scoped to the US
- skips default-list companies that were already searched and cached
- records companies without a Greenhouse board in `crawler_cache/non_greenhouse_companies.txt`
- writes a fresh `crawler_cache/matched_jobs.jsonl` snapshot on each run
- preserves archived Gregslist results under `crawler_cache/archive/`

## Requirements

- Python 3.8+
- outbound network access to `boards-api.greenhouse.io`
- the project virtual environment in `./envs`

## Usage

Run the crawler with the environment's Python interpreter:

```bash
./envs/bin/python crawl_greenhouse.py
```

If you prefer to activate the environment first:

```bash
conda activate ./envs
python crawl_greenhouse.py
```

## Options

```bash
./envs/bin/python crawl_greenhouse.py --help
```

Available flags:
- `--company`: limit the run to one or more company names; repeat the flag to provide multiple companies
- `--limit`: maximum number of companies to process from the selected company list
- `--delay`: minimum delay in seconds between API requests
- `--concurrency`: maximum number of in-flight API requests
- `--timeout`: per-request timeout in seconds
- `--show-cache-stats`: print current matched-job and archive counts, then exit
- `--show-company-list`: print the default target company list, then exit
- `--show-tracking-report`: print a report that joins the matched-job snapshot with the job/company tracking overlay files, then exit
- `--set-job-status`: upsert a job-level tracking record with one of `pending_review`, `applied`, `revisit_later`, `not_a_fit`, or `archived`
- `--company-slug`: company slug used with `--set-job-status`
- `--job-id`: Greenhouse job id used with `--set-job-status`
- `--review-date`: optional ISO review date used with `--set-job-status`
- `--application-date`: optional ISO application date used with `--set-job-status`
- `--next-action-date`: optional ISO next action date used with `--set-job-status`
- `--notes`: optional freeform notes used with `--set-job-status`
- `--match-rationale`: optional short rationale used with `--set-job-status`

Example with the default company list:

```bash
./envs/bin/python crawl_greenhouse.py --delay 0.5 --concurrency 4
```

Example limited to a few companies:

```bash
./envs/bin/python crawl_greenhouse.py --company Affirm --company Reddit --company Doximity
```

## Expected Output

The script prints a summary table like this:

```text
Company    Slug      Jobs  Matches  Status
---------  --------  ----  -------  -----------------------
Affirm     affirm      24        3  Matched jobs found
Reddit     reddit      18        1  Matched jobs found
Stealth    -            0        0  Greenhouse board not found
```

If matching jobs are found, the script also prints a `Matched Jobs` table with company, job title, location, and job URL.
It then prints a `Matched Job URLs` section with one direct URL per line for quick copy/paste.

During the run, progress messages are written to `stderr` with a `[crawler]` prefix so the final `stdout` output stays easy to scan.

## Output Files

The crawler writes results into `crawler_cache/`:

- `matched_jobs.jsonl`: the current Greenhouse-only matched-job snapshot
- `careers_scraped.jsonl`: cached search results used to skip already-searched default companies
- `non_greenhouse_companies.txt`: companies confirmed not to expose a Greenhouse board
- `job_tracking.jsonl`: job-level workflow state overlay keyed by `company_slug` and `greenhouse_job_id`
- `company_revisit.jsonl`: company-level revisit schedule overlay keyed by `company_slug`
- `archive/matched_jobs_gregslist_2026-04-21.jsonl`: archived Gregslist output preserved before the refactor

Each `matched_jobs.jsonl` line includes:
- `company_name`
- `company_slug`
- `careers_url`
- `greenhouse_job_id`
- `job_title`
- `job_url`
- `job_location`
- `matched_keywords`
- `found_date`
- `job_description`

Each `job_tracking.jsonl` line is expected to include:
- `company_slug`
- `greenhouse_job_id`
- `job_url`
- `status`
- `review_date`
- `application_date`
- `next_action_date`
- `notes`
- `match_rationale`

Each `company_revisit.jsonl` line is expected to include:
- `company_slug`
- `company_name`
- `board_type`
- `last_checked`
- `next_revisit`
- `reason`
- `notes`

You can inspect output counts without crawling:

```bash
./envs/bin/python crawl_greenhouse.py --show-cache-stats
```

You can also inspect the joined workflow state without crawling:

```bash
./envs/bin/python crawl_greenhouse.py --show-tracking-report
```

You can update a tracked job from the CLI without editing JSONL directly:

```bash
./envs/bin/python crawl_greenhouse.py \
	--set-job-status applied \
	--company-slug affirm \
	--job-id 7594302003
```

Example for saving a role for later application:

```bash
./envs/bin/python crawl_greenhouse.py \
	--set-job-status revisit_later \
	--company-slug affirm \
	--job-id 7615048003 \
	--next-action-date 2026-05-15 \
	--notes "Save for later application cadence." \
	--match-rationale "Strong backend fit for distributed systems and APIs."
```

Example for recording a reviewed non-match:

```bash
./envs/bin/python crawl_greenhouse.py \
	--set-job-status not_a_fit \
	--company-slug instacart \
	--job-id 7341203 \
	--notes "Reviewed and not a fit." \
	--match-rationale "Ads domain focus is not the current target."
```

## Notes

- The crawler filters by title families already used in the project, then stores full job descriptions for matched roles.
- The location filter is intentionally conservative: remote jobs must explicitly mention the US in the Greenhouse location field.
- Greenhouse slug resolution is heuristic-based; if a company uses an unexpected board token, it will be skipped until a better slug hint is added.
- Legacy Gregslist cache files remain in `crawler_cache/` for reference, but the new crawler does not read them.
- `matched_jobs.jsonl` remains the regenerable crawler snapshot; workflow state belongs in the overlay files so the snapshot can be refreshed safely.
