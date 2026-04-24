# agents_archive.md

## Archived Task Instructions

This file contains completed task instructions for reference, debugging, and iteration.

---

# ✅ Phase 1: Canonical Profile & Evidence Bank Extraction

**Status:** COMPLETED  
**Completion Date:** April 2026  
**Outputs:** 
- `derived_profile/canonical_profile.json`
- `derived_profile/evidence_bank.jsonl`
- `derived_profile/profile_summary.md`
- `derived_profile/open_questions.md`
- `derived_profile/style_samples.jsonl`

---

## Purpose
Build a strong **canonical candidate profile** and **evidence bank** from archived application materials (`.docx` files) to support job matching, resume/cover letter tailoring, and retrieval workflows.

## Goal
Using the `.docx` files in `resumes_cov_letters/archive`, create a trustworthy, reusable representation of the candidate's background.

Specifically:
- Parse all `.docx` files in `resumes_cov_letters/archive` recursively.
- Classify each document type when possible:
  - resume
  - cover letter
  - application question/response
  - other candidate-authored job-search material
- Extract and normalize the candidate's:
  - roles and responsibilities
  - skills and tools
  - projects
  - achievements and metrics
  - industries/domains
  - writing and communication experience
  - customer-facing/support experience
  - leadership/collaboration examples
  - preferences, motivations, and recurring themes
- Build a **canonical profile** that merges repeated facts into a single structured representation.
- Build an **evidence bank** of atomic, source-backed snippets that can later be retrieved for matching and drafting.
- Preserve provenance so every important claim can be traced back to one or more source documents.

---

## Context
- Source files will be provided in `resumes_cov_letters/archive`.
- Source materials may contain overlapping, inconsistent, or differently phrased versions of the same experience.
- Some facts may appear only once, while others may appear in many versions of a resume or cover letter.
- The canonical profile should optimize for **accuracy, traceability, and reuse**, not just readability.
- The evidence bank should be useful both for:
  - direct prompt assembly without retrieval, and
  - later hybrid retrieval / RAG if that becomes useful.

---

## Core Principles
- **Do not invent facts.** Only include information grounded in the provided documents.
- **Separate fact from inference.** If an inference is useful, label it clearly as inferred.
- **Preserve provenance.** Important claims must link back to source file(s) and text span(s).
- **Prefer evidence over polish.** The profile can be summarized later; extraction should prioritize fidelity.
- **Normalize without losing nuance.** Merge duplicates, but keep meaningful variants and context.
- **Handle contradictions explicitly.** If dates, titles, technologies, or claims conflict, flag them instead of guessing.
- **Keep evidence atomic.** Evidence entries should usually be a single accomplishment, responsibility, project description, or behavioral example.
- **Distinguish stated vs demonstrated skill.** A claimed skill is weaker than a project or quantified outcome showing that skill.

---

## Required Outputs
Create the following derived files under a new directory such as `derived_profile/`:

1. `derived_profile/canonical_profile.json`
   - Structured, normalized candidate profile.
   - Stable IDs for major entities.
   - References to supporting evidence IDs.

2. `derived_profile/evidence_bank.jsonl`
   - One JSON object per evidence item.
   - Each item should be atomic and source-backed.
   - Designed to be embedding-friendly for later retrieval.

3. `derived_profile/profile_summary.md`
   - Human-readable summary of the canonical profile.
   - Highlight strongest role families, skills, and evidence themes.

4. `derived_profile/open_questions.md`
   - Ambiguities, contradictions, missing dates, uncertain tool names, unclear employers, etc.
   - Include recommended follow-up questions only if the ambiguity materially affects matching or drafting.

Optional but encouraged:

5. `derived_profile/style_samples.jsonl`
   - High-quality candidate-authored writing samples extracted from cover letters and application responses.
   - Useful for later style conditioning or fine-tuning evaluation.

---

## Canonical Profile Requirements
The canonical profile should be a structured representation of the candidate, not just a stitched summary.

Recommended top-level sections:
- `candidate_overview`
- `target_role_families`
- `experience_history`
- `projects`
- `skills`
- `tools_and_technologies`
- `domains`
- `writing_and_communication`
- `customer_support_and_success`
- `leadership_and_collaboration`
- `achievements`
- `education_and_credentials`
- `preferences_and_motivators`
- `constraints_or_unknowns`

Recommended expectations for each section:

### candidate_overview
A concise normalized snapshot of the candidate, including:
- likely seniority band if evidenced
- broad professional identity
- recurring strengths
- strongest adjacent / transferable role families

### target_role_families
Identify role families supported by evidence, such as:
- software engineering
- technical support
- technical writing
- customer success
- solutions engineering
- developer support / developer relations
- administrative assistant / office coordinator
- data entry specialist
- customer service representative (general/non-technical)
- help desk / IT support (entry-level)
- quality assurance / testing (entry-level, manual)
- documentation specialist / proofreader / editor
- research assistant
- project coordinator / administrative project support
- sales support / inside sales / sales operations
- content moderator / reviewer
- receptionist / front desk coordinator
- scheduler / appointment coordinator
- operations assistant
- back office support

Each role family should include:
- `role_family`
- `support_level` (strong / moderate / emerging)
- `why_supported`
- `supporting_evidence_ids`

### experience_history
Normalize work experiences where possible:
- employer
- role title(s)
- date range if stated
- responsibilities
- tools used
- outcomes
- supporting evidence IDs

If exact chronology is unclear, preserve partial chronology and flag uncertainty.

### projects
Each project should capture:
- project name or short label
- project type
- problem/context
- actions taken
- tools/skills involved
- outputs or outcomes
- supporting evidence IDs

### skills
Organize skills into categories such as:
- programming / scripting
- systems / infrastructure
- documentation / writing
- troubleshooting / support
- customer communication
- collaboration / process

Each skill should include:
- `skill_name`
- `evidence_strength` (direct, repeated, inferred, weak)
- `contexts`
- `supporting_evidence_ids`

### achievements
Capture distinct, high-value accomplishments, especially those with metrics.
Each achievement should include:
- `achievement_id`
- `summary`
- `metric_or_outcome` if present
- `context`
- `supporting_evidence_ids`

### preferences_and_motivators
Extract recurring candidate preferences only when they appear in source materials, for example:
- interest in customer-facing technical roles
- preference for writing-heavy work
- motivation around helping users, clarifying complexity, improving systems, etc.

These should be marked clearly as preferences stated in application materials, not objective facts.

---

## Evidence Bank Requirements
The evidence bank is the retrieval-ready layer. It should contain **atomic, source-grounded evidence records**.

Each record should include at minimum:
- `evidence_id`
- `source_file`
- `doc_type`
- `source_location`
  - paragraph index, heading, question label, or another stable locator
- `text`
  - minimally cleaned original snippet
- `normalized_summary`
  - short paraphrase of what this evidence supports
- `evidence_type`
  - achievement / responsibility / project / skill demonstration / writing sample / preference / education / leadership / customer interaction / troubleshooting / other
- `role_tags`
  - e.g. software_engineering, tech_support, technical_writing, customer_success
- `skill_tags`
  - normalized skills/tools referenced or strongly implied
- `domain_tags`
  - SaaS, developer tools, B2B, education, etc. when evidenced
- `strength`
  - strong / medium / weak
- `is_quantified`
- `dates_mentioned`
- `organization_or_project`
- `canonical_entity_refs`
  - IDs in the canonical profile this evidence supports
- `notes`
  - ambiguity, contradiction, or extraction notes if needed

Preferred properties:
- one clear idea per evidence record
- enough surrounding context to remain meaningful when retrieved alone
- no unnecessary fragmentation into tiny sentence shards
- no large multi-topic chunks when they can be split cleanly

---

## Extraction and Normalization Workflow
Agents should follow this workflow:

### 1. Ingest
- Recursively discover `.docx` files under `resumes_cov_letters/archive`.
- Ignore temporary Office files and non-candidate documents.
- Preserve original filenames and relative paths.

### 2. Parse
- Extract paragraphs, headings, bullet lists, tables, and question/answer sections.
- Preserve approximate document structure where possible.
- Keep enough indexing information to trace each snippet back to its source location.

### 3. Classify document type
Infer whether each file is primarily:
- resume
- cover letter
- application Q/A
- mixed or unknown

### 4. Extract atomic claims and evidence
From each document, identify:
- employers, titles, projects, tools, domains
- accomplishments and metrics
- support/troubleshooting examples
- writing/documentation examples
- customer-facing or cross-functional work
- motivations and role preferences

### 5. Normalize entities
Normalize repeated variants such as:
- tool names (`JS` -> `JavaScript` where appropriate)
- company names with small formatting differences
- repeated project descriptions across different resume versions
- role family labels that map to a shared concept

Normalization should never erase the original wording in the evidence bank.

### 6. Deduplicate carefully
- Merge semantically duplicated evidence when it is clearly the same underlying claim.
- Preserve multiple source references for the merged concept.
- Do not collapse distinct examples just because they mention the same skill.

### 7. Score evidence strength
Use a simple evidence hierarchy:
- **Strong**: quantified outcomes, concrete project work, clear actions and results
- **Medium**: specific responsibilities or examples without metrics
- **Weak**: generic self-descriptions or unsupported claims

### 8. Build the canonical profile
- Prefer repeated, well-supported facts.
- Store references to supporting evidence IDs.
- Keep contradictory information in `constraints_or_unknowns` or `open_questions.md`.

### 9. Produce human-readable summaries
Generate summaries that are useful for later prompting, but do not let summaries replace the structured data and evidence layer.

---

## What Makes the Profile Strong
A strong canonical profile should:
- represent the candidate as a **set of reusable capabilities and evidence-backed themes**, not a single frozen resume
- make transferable strengths easy to identify across multiple role families
- distinguish between:
  - direct experience
  - adjacent experience
  - plausible transferability
- surface the candidate's strongest proof points for:
  - technical execution
  - troubleshooting/support
  - documentation/writing
  - customer empathy and communication
  - collaboration and ownership
- preserve quantified results whenever available
- retain enough granularity that later systems can select evidence specific to a job description

A weak profile would simply concatenate resume bullets, lose provenance, flatten all skills into one list, and fail to distinguish strong evidence from generic claims.

---

## What Makes the Evidence Bank Strong
A strong evidence bank should:
- contain **retrieval-ready**, self-contained evidence snippets
- include metadata that helps filter by role family, skill, domain, and evidence type
- preserve the candidate's original phrasing where useful
- include multiple examples for the same skill when they demonstrate different contexts
- make it easy to answer prompts like:
  - "What evidence supports technical writing roles?"
  - "What customer-facing troubleshooting examples exist?"
  - "Which projects best demonstrate software engineering ability?"
  - "What achievements include metrics?"

---

## Constraints
- Do not modify source `.docx` files.
- Do not hallucinate employers, tools, dates, responsibilities, or outcomes.
- Do not silently resolve contradictions.
- Do not treat cover-letter enthusiasm alone as proof of a skill.
- Prefer structured outputs that are easy to diff and extend.
- Keep IDs stable where possible so future runs can merge new material.
- The resulting data model should support both:
  - direct prompting with a compact canonical profile, and
  - later embedding / retrieval of evidence records.

---

## Done When
This task is done when:
- all `.docx` files in `resumes_cov_letters/archive` have been parsed
- a structured `canonical_profile.json` exists
- a source-backed `evidence_bank.jsonl` exists
- a readable `profile_summary.md` exists
- ambiguities and contradictions are listed in `open_questions.md`
- major skills, projects, achievements, and role-family evidence are linked back to source materials
- the outputs are usable for downstream job matching and tailored application drafting

---

## Guidance for Codex
- Use Python and reliable `.docx` parsing libraries.
- Favor clear, modular code with explicit schemas.
- Store intermediate parsing artifacts if they help debugging.
- Include tests or validation checks for:
  - missing source paths
  - empty parsed documents
  - malformed JSON/JSONL output
  - duplicate IDs
- Add lightweight validation to ensure every major canonical claim has supporting evidence.
- When in doubt, keep more provenance rather than less.
- Build this so new `.docx` files can be added later and the profile can be regenerated safely.

---

## Suggested Output Shape

### Example canonical profile snippet
```json
{
  "candidate_overview": {
    "professional_identity": "Technical professional with evidence across software, support, and writing-heavy work",
    "recurring_strengths": [
      "troubleshooting",
      "technical communication",
      "cross-functional collaboration"
    ]
  },
  "target_role_families": [
    {
      "role_family": "technical_writing",
      "support_level": "strong",
      "why_supported": "Multiple source documents include documentation, explanation, and communication-focused examples.",
      "supporting_evidence_ids": ["ev_014", "ev_037"]
    }
  ]
}
```

### Example evidence record
```json
{
  "evidence_id": "ev_014",
  "source_file": "resumes_cov_letters/archive/cover_letters/company_x_cover_letter.docx",
  "doc_type": "cover_letter",
  "source_location": "paragraph_12",
  "text": "I translated complex technical issues into plain language for customers and internal teams...",
  "normalized_summary": "Demonstrates technical communication and customer-facing explanation skills.",
  "evidence_type": "skill_demonstration",
  "role_tags": ["technical_writing", "tech_support", "customer_success"],
  "skill_tags": ["technical communication", "customer communication", "troubleshooting"],
  "domain_tags": [],
  "strength": "medium",
  "is_quantified": false,
  "dates_mentioned": [],
  "organization_or_project": null,
  "canonical_entity_refs": ["skill_technical_communication"],
  "notes": "Good cross-role evidence; not quantified."
}
```
