# agents.md

## Project Overview

This file provides current task instructions for AI agents working on the job application automation system.

## Agent Handoff Status (2026-04-22)

### Completed In This Repo Since The Original Plan

- `scripts/generate_application_materials.py` was refactored into a thin entrypoint plus role-aware modules:
  - `scripts/application_materials_pipeline.py`
  - `scripts/application_materials_templates.py`
- `scripts/generate_application_materials.py` was tightened so the most stable resume sections are now archive-backed instead of being fully regenerated each run.
- Resume generation now keeps experience, project, and professional-development bullets substantially stable and only varies the job-aware `TECHNICAL SKILLS` headings plus summary text.
- Cover-letter generation was tightened to reduce repetition by relying on more deterministic, archive-backed paragraphs.
- DOCX rendering in `scripts/generate_application_materials.py` now includes template-anchor safety checks.
- `crawl_greenhouse.py` now supports workflow overlays via `crawler_cache/job_tracking.jsonl` and `crawler_cache/company_revisit.jsonl`.
- `crawl_greenhouse.py --show-tracking-report` now joins the matched-job snapshot with overlay state.
- `crawl_greenhouse.py --set-job-status ...` now lets agents or users mark jobs from the CLI instead of editing JSONL directly.
- `crawl_greenhouse.py` now separates title matching into explicit role families for software engineering, solutions engineering, technical support engineering, and technical writing.
- `crawl_greenhouse.py` now persists `matched_role_families` on future matched-job snapshots.
- `crawl_greenhouse.py` default target companies were expanded with the next batch of candidate companies from `plan.txt`, and the expanded crawl state has now been refreshed.
- Current tracked state already includes the applied Affirm PMI role, the applied Instacart Logistics Foundation role, later-application Affirm roles, reviewed-not-a-fit jobs, and company revisit dates for Affirm and Instacart.
- `scripts/generate_application_materials.py` now has an initial customer-facing technical-role generation path that uses the Plenful implementation-specialist templates in `application_materials/` for solutions/support/writing-style roles.
- Initial adjacent-role validation ran successfully on Affirm `7666749003` (Senior Technical Account Manager), and the generated metadata resolved to `solutions_engineering` with the implementation-specialist resume and cover-letter templates.
- Technical writing now has a separate template path using the writer examples under `application_materials/reference_examples/technical_writing/`.
- The technical-writing resume path now lightly tailors competency headings to the job description while keeping the writer template bodies stable.

### Current Working State

- `crawler_cache/matched_jobs.jsonl` remains the regenerable crawler snapshot and should not be used for workflow edits.
- Workflow state belongs in:
  - `crawler_cache/job_tracking.jsonl`
  - `crawler_cache/company_revisit.jsonl`
- `README.md` documents the current crawler/reporting and job-status CLI workflow.
- The adjacent-role generation path currently uses:
  - `application_materials/reference_examples/customer_facing_technical/vargas_technical_implementation_specialist_resume.docx`
  - `application_materials/reference_examples/customer_facing_technical/vargas_technical_implementation_specialist_cover_letter.docx`
- Those Plenful reference files now live in `application_materials/reference_examples/customer_facing_technical/`.
- Solutions/support roles still share the Plenful implementation-specialist template path, while `technical_writing` now uses:
  - `application_materials/reference_examples/technical_writing/vargas_technical_writer_resume_core_competencies.docx`
  - `application_materials/reference_examples/technical_writing/vargas_technical_writer_cover_letter_sprypoint.docx`
- `crawler_cache/matched_jobs.jsonl` was refreshed on 2026-04-22 after the expanded company-seed update and now persists `matched_role_families` in the live snapshot.
- The refreshed snapshot currently contains 96 matched jobs total: 92 `software_engineering` matches and 4 `solutions_engineering` matches (Affirm TAM `7666749003`, Huntress Technical Account Manager III `7621237003`, Airtable Senior Partner Solutions Architect `8461582002`, Airtable Senior Solutions Architect `8487502002`); there are still no live `technical_support_engineering` or `technical_writing` matches yet.
- The current report command is:
  - `./envs/bin/python crawl_greenhouse.py --show-tracking-report`
- The current job-status update command is:
  - `./envs/bin/python crawl_greenhouse.py --set-job-status <status> --company-slug <slug> --job-id <id> ...`

### Start Here

Use these commands first before making broader changes:

```bash
# Inspect the current workflow state and due revisits
./envs/bin/python crawl_greenhouse.py --show-tracking-report

# Inspect crawler/cache counts
./envs/bin/python crawl_greenhouse.py --show-cache-stats

# Re-generate the current seed software-engineering example
./envs/bin/python scripts/generate_application_materials.py \
  --url https://job-boards.greenhouse.io/affirm/jobs/7594302003

# Re-generate the current adjacent-role validation example
./envs/bin/python scripts/generate_application_materials.py \
  --url https://job-boards.greenhouse.io/affirm/jobs/7666749003

# Mark a job as applied / revisit_later / not_a_fit without editing JSONL directly
./envs/bin/python crawl_greenhouse.py \
  --set-job-status applied \
  --company-slug affirm \
  --job-id 7594302003

# Example: store a later-application follow-up role
./envs/bin/python crawl_greenhouse.py \
  --set-job-status revisit_later \
  --company-slug affirm \
  --job-id 7615048003 \
  --next-action-date 2026-05-15 \
  --notes "Save for later application cadence." \
  --match-rationale "Strong backend fit for distributed systems and APIs."
```

### Not Started Yet

- The adjacent-role slice is only partially implemented end to end; one customer-facing template path now exists, but it still needs broader validation across technical support and technical writing examples.
- The Plenful technical implementation specialist materials are now wired in as the shared customer-facing path for solutions/support roles.
- Technical writing now has a dedicated template path, but it still needs validation against a real matched technical-writing job because none are live in the current snapshot.
- The expanded company discovery pass has started populating cache state for the next batch of companies from `plan.txt`; some newly found Greenhouse boards produced additional solutions matches, but no live support/writing matches yet.
- The crawler role-family split is implemented and the current `crawler_cache/matched_jobs.jsonl` snapshot now includes `matched_role_families`, but only one adjacent-role example is currently present in live data.
- No decision has been finalized to create a second fine-tuned model for adjacent roles; that evaluation is still pending.

### Recommended Next Steps For The Next Agent

1. Validate the adjacent-role generation path on additional real examples beyond the Affirm TAM role, especially technical-support and technical-writing titles if or when they appear in the snapshot.
2. Treat the Plenful implementation-specialist template as the current shared base for solutions/support roles unless new examples show structural mismatch.
3. Validate the new technical-writing template path against the first live `technical_writing` match that appears in the snapshot.
  When a live `technical_writing` match appears, run the full document-generation path against that job before changing the writer templates again.
4. Review the newly discovered Airtable and Huntress solutions-role matches and decide whether either should be marked for later application or not-a-fit in the workflow overlays.
5. Add a company-revisit CLI helper similar to `--set-job-status` so revisit dates and notes can also be maintained from the command line.
6. Only recommend a second model if the adjacent-role generation path still requires heavy manual rewriting after prompt/template-based evaluation.

### Project Phases

| Phase | Status | Description | Archive |
|-------|--------|-------------|---------|
| **Phase 1** | ✅ Completed | Canonical Profile & Evidence Bank Extraction | [agents_archives/phase_1_profile_extraction.md](agents_archives/phase_1_profile_extraction.md) |
| **Phase 2** | ✅ Completed | Fine-Tuning for Application Writing | [agents_archives/phase_2_finetuning_prep.md](agents_archives/phase_2_finetuning_prep.md) |
| **Phase 3** | 📋 Ready to Start | Inference Pipeline & Job Matching | [agents_archives/phase_3_inference_pipeline.md](agents_archives/phase_3_inference_pipeline.md) |
| **Phase 3.5** | ✅ Completed | Enhanced Job Crawler with Caching & Job Title Matching | [agents_archives/phase_3_5_enhanced_job_crawler.md](agents_archives/phase_3_5_enhanced_job_crawler.md) |
| **Phase 3.6** | 🔧 In Progress | Workday ATS API Integration | (current file) |
| **Phase 4** | 🚧 Planned | Greenhouse-Only Job Crawler | (see below) |
| **Phase 5** | 🔧 In Progress | Automated Application Generation | (see below) |


### Completed Outputs
- `derived_profile/canonical_profile.json` - Structured candidate profile
- `derived_profile/evidence_bank.jsonl` - Atomic, source-backed evidence records
- `derived_profile/profile_summary.md` - Human-readable profile summary
- `derived_profile/open_questions.md` - Ambiguities and contradictions
- `derived_profile/style_samples.jsonl` - Writing samples for style conditioning
- `training_data/application_writing_training.jsonl` - Fine-tuning training dataset
- `scripts/build_training_data.py` - Training data generation pipeline
- `scripts/validate_training_data.py` - Training data validation script
- `upload_training_data.py` - Upload helper configured for the application-writing dataset
- `crawl_greenhouse.py` - Greenhouse-only crawler with title matching and job-detail fetching
- `test_workday_api.py` - Test script for Workday API job fetching
- `workday_api.md` - Workday API documentation and request details
- `crawler_questions.md` - Web scraping concepts: robots.txt, JavaScript, APIs
- `README.md` - Crawler usage and cache documentation
- `scripts/generate_application_materials.py` - Separate generation pipeline for tailored resumes and cover letters
- `application_materials/generated/` - First-pass generated application outputs and normalized job descriptions
---

# 🚧 Phase 5: Automated Application Generation

**Goal:**
Build a separate inference pipeline that takes a matched job URL, retrieves the job description, calls `OPENAI_FINETUNED_MODEL`, and produces a customized resume and cover letter in `.docx` format that matches the example application materials exactly.

## Scope Separation

- Keep this work separate from crawler maintenance and enhancements.
- Use a dedicated script for generation rather than adding this logic to `crawl_greenhouse.py`.
- Store generated outputs in a dedicated directory so crawler artifacts and application artifacts do not mix.

## Inputs for Initial Testing

- Affirm: `https://job-boards.greenhouse.io/affirm/jobs/7594302003`
- Instacart: `https://www.instacart.careers/job?id=7831409`

## Implementation Tasks

1. **Create a Separate Generation Pipeline**
  - Add a dedicated script, for example `scripts/generate_application_materials.py`.
  - Load `OPENAI_FINETUNED_MODEL` from the existing config.

2. **Fetch and Normalize Job Descriptions**
  - Retrieve the job description from each source URL.
  - Support both Greenhouse and non-Greenhouse sources needed for testing.
  - Save normalized job description text for reproducibility and debugging.

3. **Generate Tailored Documents**
  - Call the fine-tuned model with the normalized job description plus the canonical candidate profile/evidence context.
  - Generate both a tailored resume and a tailored cover letter.
  - Keep outputs grounded in the canonical profile and evidence bank only.

4. **Match Existing Document Formats Exactly**
  - Use the example `.docx` files in `application_materials/Archive/` as formatting templates.
  - Ensure the final resume and cover letter preserve the same document structure, layout, and style conventions as the examples.
  - Output final files as `.docx`, not markdown or plain text.

5. **Testing and Validation**
  - Test the full flow on the two seed URLs above.
  - Validate that the generated content is job-specific and evidence-grounded.
  - Validate that produced `.docx` files match the example materials' formatting expectations.

## Current Status

- A separate generation script now exists at `scripts/generate_application_materials.py`.
- The pipeline successfully fetched and normalized the two seed job descriptions.
- `.docx` and `.txt` outputs were generated for:
  - Affirm
  - Instacart
- Generated outputs are stored under `application_materials/generated/`.
- Resume generation is now more stable because key sections are archive-backed and the main remaining work is confirming template fidelity plus extending the approach to adjacent role families.

## Suggested Outputs

- `scripts/generate_application_materials.py` - Main generation pipeline
- `application_materials/generated/` - Generated resume and cover letter outputs
- `application_materials/generated/job_descriptions/` - Saved normalized job descriptions used for generation

## Success Criteria

- Job description text is successfully retrieved from both test URLs.
- The pipeline calls `OPENAI_FINETUNED_MODEL` successfully.
- A tailored cover letter and resume are generated for each test job.
- Final outputs are `.docx` files that match the example application materials' formatting.

## Remaining Follow-Up

1. **Validate Template Fidelity**
  - Compare generated `.docx` files directly against the chosen archive templates.
  - Confirm section lengths and paragraph replacement logic preserve the exact expected layout.

2. **Harden Generation Logic**
  - Improve handling of non-Greenhouse job URLs beyond the current initial support.
  - Consider adding deterministic post-processing constraints for resume bullets and cover-letter paragraphs.

3. **Add Adjacent-Role Generation Path**
  - Use the Plenful technical implementation specialist examples to define a customer-facing technical-role template path.
  - Evaluate technical support, solutions engineer, and technical writer outputs with prompt/template changes before considering a second fine-tune.

---

# ✅ Phase 4: Greenhouse-Only Job Crawler (Archived)

**Summary:**
Replaced the Gregslist-centric crawler with a Greenhouse-focused crawler that queries a set of target companies directly via the Greenhouse public API. Gregslist outputs archived, and the crawler now only targets Greenhouse job boards for a curated company list.

---

# ✅ Greenhouse Crawler Enhancements (Archived)

**Summary:**
Greenhouse crawler now maintains a dynamic company list, skips already-searched companies, filters for US-remote or Austin, TX jobs, and tracks non-Greenhouse companies in a separate file. All matched job URLs are printed and results are stored in `matched_jobs.jsonl`.

---

# ✅ Greenhouse Crawler Company List Expansion (Archived)

**Summary:**
Non-Greenhouse companies are now tracked in `non_greenhouse_companies.txt` and removed from the active crawler list. The Greenhouse target list has been expanded with new companies. The crawler continues to filter jobs by location (US-remote or Austin, TX), prints matched job URLs, and updates `matched_jobs.jsonl`.

---

# 🚧 Ongoing: Greenhouse Crawler Maintenance & Company Discovery

1. **Maintain Company Lists**
   - Keep `non_greenhouse_companies.txt` up to date as new companies are checked.
   - Only keep confirmed Greenhouse companies in the active target list.

2. **Add New Companies**
   - When new companies are identified, add them to the target list and check for Greenhouse job boards.

3. **Continue Filtering and Bookkeeping**
   - Continue to skip already-searched companies and filter jobs by location (US-remote or Austin, TX).
   - Print matched job URLs and update `matched_jobs.jsonl`.
   - Maintain `non_greenhouse_companies.txt` for bookkeeping.
  - Maintain `job_tracking.jsonl` and `company_revisit.jsonl` as the workflow overlays.
  - Prefer the CLI helpers in `crawl_greenhouse.py` over manual JSONL edits when updating job workflow state.

---

### Current Working Directories
```
application_materials/
  ├── Archive/          # Source resumes and cover letters (.docx)
  └── job_descriptions/ # Real job postings for training data
agents_archives/        # Completed phase instructions
derived_profile/        # Canonical profile and evidence bank
training_data/          # Fine-tuning datasets
scripts/                # Data preparation and validation scripts
crawler_cache/          # Persistent crawler state and matched-job outputs
  ├── no_careers_page.txt
  ├── careers_scraped.jsonl
  ├── matched_jobs.jsonl
  ├── job_tracking.jsonl
  └── company_revisit.jsonl
```

---

## Core Principles (Apply Across All Phases)

- **Do not invent facts.** Only include information grounded in the provided documents or canonical profile.
- **Separate fact from inference.** If an inference is useful, label it clearly as inferred.
- **Preserve provenance.** Important claims must link back to source file(s) and text span(s).
- **Prefer evidence over polish.** Prioritize fidelity and accuracy over stylistic refinement.
- **Normalize without losing nuance.** Merge duplicates, but keep meaningful variants and context.
- **Handle contradictions explicitly.** If dates, titles, technologies, or claims conflict, flag them instead of guessing.
- **Keep evidence atomic.** Evidence entries should be single, focused accomplishments or examples.
- **Distinguish stated vs demonstrated skill.** A claimed skill is weaker than a project or quantified outcome.

# 🚧 Phase 3.6: Workday ATS API Integration

## Purpose
Extend the crawler to handle Workday-based job boards via direct API calls instead of HTML parsing. Workday is a common ATS platform used by many large companies, and its JavaScript-heavy pages are difficult to crawl with traditional methods.

## Context
- The existing crawler (`crawl_gregslist.py`) already recognizes Workday domains (`myworkdayjobs.com`, `workdayjobs.com`)
- Workday job boards use JavaScript to dynamically load listings, making them invisible to basic HTML crawlers
- However, Workday exposes a predictable JSON API that's much faster and more reliable than browser automation

## API Pattern Discovery

### Identifying Workday Sites
When the crawler encounters a URL matching Workday domains:
```
https://{company}.wd5.myworkdayjobs.com/{site-name}/
```

Instead of parsing HTML, make an API call to:
```
POST https://{company}.wd5.myworkdayjobs.com/wday/cxs/{company}/{site-name}/jobs
```

### Request Format
```json
{
  "appliedFacets": {},        // Filters (location, remote, etc.)
  "limit": 20,                 // Results per page
  "offset": 0,                 // Pagination offset
  "searchText": "python"       // Search keyword
}
```

### Response Format
```json
{
  "jobPostings": [
    {
      "title": "Senior Software Engineer",
      "externalPath": "/job/Remote-US/Senior-Software-Engineer_R-12345",
      "locationsText": "Remote",
      "remoteType": "Remote",
      "postedOn": "Posted Yesterday",
      "bulletFields": ["R-12345"]
    }
  ],
  "total": 47
}
```

## Implementation Tasks

### 1. Add Workday API Handler
Create `fetch_workday_jobs()` function that:
- Detects Workday URLs (already done via `is_known_ats_domain()`)
- Extracts company name and site name from the URL
- Constructs the API endpoint
- Makes POST request with search parameters
- Returns parsed JSON response

### 2. Integrate with Title Matching
Use existing `infer_keywords()` and title pattern matching:
- Filter `jobPostings` array by target job titles
- Create `MatchedJob` records from API results
- Append to `matched_jobs.jsonl` as normal

### 3. Handle Pagination
Workday APIs support pagination via `offset`:
- First 20 jobs: `offset=0`
- Next 20 jobs: `offset=20`
- Continue until `len(jobPostings) < limit`

### 4. Extract Facet IDs (Optional)
Some Workday sites use facet IDs for filters (location, job type):
- Check URL parameters: `?a=facet_id&c=category_id`
- These can be passed in `appliedFacets` for targeted searches
- For broad discovery, leave `appliedFacets` empty

## Reference Implementation
See `test_workday_api.py` for a working example using Red Hat's Workday instance.

## Benefits Over HTML Parsing
- ✅ **50-100x faster** - Direct API calls vs rendering JavaScript
- ✅ **More reliable** - Structured JSON vs fragile HTML selectors
- ✅ **Pagination built-in** - Simple offset parameter
- ✅ **Clean data** - Job details already structured
- ✅ **No browser needed** - Standard HTTP requests

## Integration Points
1. Modify `_find_careers_page()` to detect Workday URLs early
2. Call Workday API handler instead of fetching HTML
3. Parse JSON and create `MatchedJob` records
4. Return to main crawler flow

## Success Criteria
- Crawler can extract jobs from Workday sites without HTML parsing
- Job matching works identically to traditional HTML-based extraction
- Results are cached and deduplicated normally
- Workday API calls respect rate limiting

## Related Files
- `test_workday_api.py` - Working API test script
- `workday_api.md` - Captured API request details
- `crawler_questions.md` - Context on JavaScript vs API approaches
- `crawl_greenhouse.py` - Main crawler entrypoint for Greenhouse-based job discovery

---

# 📋 Phase 3: Inference Pipeline & Job Matching

**Status:** Ready to start (detailed plan archived)  
**See:** [agents_archives/phase_3_inference_pipeline.md](agents_archives/phase_3_inference_pipeline.md)

## Quick Overview
Build end-to-end inference that converts matched jobs + candidate profile → tailored applications:
1. Evidence retrieval from canonical profile
2. Job description normalization
3. Application generation via fine-tuned model
4. Output validation against evidence bank
5. Human review workflow

**Key Deliverables:** `scripts/retrieve_evidence.py`, `scripts/run_inference.py`, `inference_outputs/` directory
3. Implement evidence retrieval against the canonical profile and evidence bank
4. Build the first inference script using one or two held-out job descriptions
5. Add validation before scaling to crawler-discovered jobs
