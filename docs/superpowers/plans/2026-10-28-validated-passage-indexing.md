# Validated Passage Indexing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make two-stage indexing consume the active validated passage generation and provide an offline evaluation question handoff.

**Architecture:** Extend indexer configuration with the active run paths. Load and validate the selected dataset before touching Chroma; reconcile paper and passage records by stable IDs, text, and citation metadata. Keep model inference injectable in tests.

**Tech Stack:** Python 3.11+, ChromaDB, unittest, existing `research_pipeline.datasets` loader.

**Spec:** `docs/superpowers/specs/2026-10-28-validated-passage-indexing-design.md`

## Global Constraints
- Do not merge into `main`.
- Never index unvalidated pages or a mixed generation.
- Preserve physical page number and source character offsets.
- No model download or network access in tests.

## Review Focus
- Missing or corrupt active pointer must not mutate index.
- Manifest and active generation corpus mismatch must not mutate index.
- Repeated indexing and changed generation must not leave stale vectors.
- Blank pages or partial generations must not enter the index.
- Two-stage candidate filtering must return only active paper IDs.

---

### Task 1: Validated source and index reconciliation

**Files:** `src/indexing_pipeline/config.py`, `src/indexing_pipeline/indexing.py`, `tests/test_indexing_pipeline.py`

**Interfaces:** `PaperIndexer(config, embedding_function=None)` loads `load_active_dataset(run_root, pointer_path)` for indexing; `index_papers()` and `index_chunks()` retain their count return values; `search_two_stage()` retains its query interface.

- [x] Write offline tests using a temporary published dataset and local Chroma for validated chunk IDs, offsets, idempotence, stale removal, and failure before mutation.
- [x] Run tests and confirm they fail for missing behavior.
- [x] Implement the smallest production changes to pass.
- [x] Run targeted tests and the full suite.
- [x] Commit code and tests on the feature branch.

### Task 2: Evaluation handoff and documentation

**Files:** `evaluation/benchmark_questions.json`, `README.md`, `docs/chunking_evaluation_plan.md`

**Interfaces:** Question records contain `id`, `question`, and `intent`; labels will be added only after human review.

- [x] Add representative business questions tied to the 25-paper corpus as a candidate set, explicitly unscored.
- [x] Document how to build the active dataset before indexing and how to run the offline tests.
- [x] Explain the label and scoring handoff without claiming measured retrieval quality.
- [x] Verify JSON structure, documentation commands, and full tests.
- [x] Commit documentation on the feature branch.

## Verification record

- Offline suite: 112 tests passed on the feature branch.
- Active corpus: 25 papers, 663 pages, 1,774 verified passages.
- Full-corpus deterministic embedding index: 25 papers and 1,774 passages indexed in a temporary Chroma database.
- MiniLM index command: first run updated 25 paper and 1,774 passage vectors; an offline rerun updated zero of each.
- Question set: eight unique candidate prompts, not yet human labeled or scored.
