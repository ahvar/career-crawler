# agents.md

## Project Overview

This file provides task instructions for AI agents working on the job application automation system.

### Project Phases

| Phase | Status | Description | Archive |
|-------|--------|-------------|---------|
| **Phase 1** | ✅ Completed | Canonical Profile & Evidence Bank Extraction | [phase_1_profile_extraction.md](phase_1_profile_extraction.md) |
| **Phase 2** | ✅ Completed | Fine-Tuning for Application Writing | [phase_2_finetuning_prep.md](phase_2_finetuning_prep.md) |
| **Phase 3** | 📋 Ready to Start | Inference Pipeline & Job Matching | (current file) |

### Completed Outputs
- `derived_profile/canonical_profile.json` - Structured candidate profile
- `derived_profile/evidence_bank.jsonl` - Atomic, source-backed evidence records
- `derived_profile/profile_summary.md` - Human-readable profile summary
- `derived_profile/open_questions.md` - Ambiguities and contradictions
- `derived_profile/style_samples.jsonl` - Writing samples for style conditioning
- `training_data/application_writing_training.jsonl` - Fine-tuning training dataset
- `upload_training_data.py` - Configured for gpt-4o-mini-2024-07-18

### Directory Structure
```
application_materials/
  ├── Archive/          # Source resumes and cover letters (.docx)
  └── job_descriptions/ # Real job postings for training data
docs/archive/agents_archives/  # Completed phase instructions
derived_profile/        # Canonical profile and evidence bank
training_data/          # Fine-tuning datasets
scripts/                # Data preparation and validation scripts
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

---

# 📋 Phase 3: Inference Pipeline & Job Matching

## Purpose
Build the end-to-end inference pipeline that automates job application generation using the fine-tuned model.

## Prerequisites
Ensure these outputs from previous phases exist:
- ✅ Phase 1: Canonical profile and evidence bank
- ✅ Phase 2: Fine-tuned model ready (model ID saved after training)
- ✅ `derived_profile/canonical_profile.json` - Complete and validated
- ✅ `derived_profile/evidence_bank.jsonl` - Strong evidence across role families
- ✅ `training_data/application_writing_training.jsonl` - Training dataset
- ✅ Fine-tuned model ID from OpenAI

---

## 🚧 Tasks Pending

This phase will include:
1. **Evidence Retrieval System** - Select most relevant evidence for each job
2. **Inference Pipeline** - Call fine-tuned model with job description + evidence
3. **Quality Assurance** - Validate generated applications for accuracy and style
4. **Human-in-the-Loop Review** - Interface for reviewing/editing before submission
5. **Integration with Crawler** - Connect to job matching workflow

**Status:** Awaiting manual fine-tuning completion and model ID before proceeding.

---

## Next Steps

**Manual actions required:**
1. Upload training data: `python upload_training_data.py --file training_data/application_writing_training.jsonl`
2. Monitor fine-tuning job in OpenAI dashboard
3. Save fine-tuned model ID when training completes
4. Return here to define Phase 3 detailed tasks

If you want additional validation before uploading, create `scripts/validate_training_data.py` to check:
- Valid JSONL format (one JSON object per line)
- Each example has "messages" array
- Messages have required "role" and "content" fields
- Roles follow proper sequence (system → user → assistant)
- Content is non-empty and within token limits
- No PII leakage beyond what's appropriate for the candidate's materials

---

## Constraints and Considerations

### Do:
- Use real examples from the candidate's archive as primary training data
- Maintain factual accuracy - never train on invented experiences
- Preserve the candidate's authentic communication style
- Include diverse examples across all target role families
- Test the fine-tuned model on held-out job descriptions

### Do not:
- Invent work experience, skills, or achievements not in the canonical profile
- Include generic template language unsupported by evidence
- Train on low-quality or poorly-tailored historical applications
- Overfit to specific companies or narrow role types
- Expose unnecessary personal information in training data

### Cost considerations:
- gpt-4o-mini fine-tuning: ~$3 per million training tokens
- Base inference cost is low, fine-tuned adds small multiplier
- Budget for 2-3 training iterations to refine quality
- Consider starting with smaller dataset (100-200 examples) for initial validation

---

## Success Criteria

This task is successful when:
1. `training_data/application_writing_training.jsonl` contains 100+ high-quality examples
2. Each training example pairs real job descriptions with actual cover letters/resumes
3. Training data uses JSONL format compatible with OpenAI fine-tuning API
4. `upload_training_data.py` is configured with correct paths and base model
5. All examples are grounded in real evidence (no invented experience)
6. Dataset includes diversity across target role families

**Later evaluation criteria (after you complete fine-tuning):**
- Model generates cover letters that select relevant evidence for each job description
- Writing style matches the candidate's authentic voice
- Content is tailored to role requirements
- No hallucinated or unsupported claims

---

## Deliverables

When this task is complete, you should have:
1. `training_data/application_writing_training.jsonl` - Training dataset (100+ examples)
2. `scripts/build_training_data.py` - Script to generate training data from archive + job descriptions
3. Updated `upload_training_data.py` - With correct paths and model configuration
4. Optional: `scripts/validate_training_data.py` - Data validation script

**Next steps (manual):**
1. Run validation script if created
2. Upload training data: `python upload_training_data.py --file training_data/application_writing_training.jsonl`
3. Monitor fine-tuning job in OpenAI dashboard
4. Save fine-tuned model ID for inference pipeline (Phase 3)

---

## Next Steps After Fine-Tuning (Phase 3)

Once you've completed fine-tuning manually and have a fine-tuned model ID:
1. Build an inference pipeline that takes (job_description + canonical_profile + evidence_bank) → tailored application
2. Create evaluation harness to test quality on diverse job descriptions
3. Implement evidence retrieval to select most relevant evidence for each job
4. Add human-in-the-loop review workflow for generated applications
5. Iterate on training data based on inference quality
