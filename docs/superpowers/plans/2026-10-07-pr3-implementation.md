# PR3 Implementation Plan

> For agentic workers: use superpowers:executing-plans and TDD. The user has
> explicitly approved direct local implementation; no further approval pause.

**Goal:** Produce reconstructable citation-preserving passages and safe local
datasets for subsequent embedding experiments.

**Architecture:** Pure chunk contracts and deterministic algorithms consume
validated existing page records. An optional local tokenizer adapter enforces
real budgets. A versioned generation publisher and validating loader support
the combined runner and standalone chunk CLI without altering PR1/PR2 paths.

**Tech Stack:** Python 3.11+, unittest, existing pypdf/fonttools pins, optional
`tokenizers==0.23.2` in a separate requirements file.

**Spec:** `docs/superpowers/specs/2026-10-07-pr3-citation-preserving-chunking-design.md`

## Global Constraints

- Local only; no commits, pushes, PRs, external messages, or GitHub changes.
- Preserve the original dirty checkout; execute in the existing isolated 1D clone.
- Independently develop for Team 1D; learn from but do not copy Team 1F.
- Retain standard-library ingestion and the patched PDF pins.
- Preserve exact page text, Unicode code-point offsets, citation fields, and hashes.
- Three profiles: boundary_characters (default 1800/200), fixed_characters
  (1800/200), optional tokenizer (200 content tokens/40 overlap/256 total).
- Tokenizer mode is local-only; disable tokenizer truncation/padding; no model weights.
- Publication uses complete immutable generations and one atomic active pointer.
- Benchmark questions/labels stay outside the corpus; evaluation is documentation only.

## Review Focus

- Tiny budgets and overlap near size: require progress and full coverage.
- Same hash-valid data with contradictory metadata/IDs/offsets: reject on loading.
- Source mutation during parsing: reject before publishing any pointer.
- Partial/no-text papers and malformed page collections: never report success falsely.
- Pointer/directory failures and path aliases: preserve active data and inputs.

## Task 1: Deterministic character chunks and contracts

**Files:** Create `src/research_pipeline/chunking.py`,
`tests/test_chunking.py`, `tests/pr3_fixtures.py`.

**Interfaces:** Consumes ExtractedPage/PaperMetadata. Produces frozen
`ChunkingConfig`, `CitationChunk`, `chunk_page(page, config, tokenizer=None)`,
`build_chunks(pages, papers, config, tokenizer=None)`,
`validate_chunks(chunks, pages, papers)` and SHA-256 helpers.

- [ ] Write tests for exact fixed windows (size 6, overlap 2), preferred ends,
  source slicing, full Unicode coverage, whitespace, invalid settings, duplicate
  pages, inconsistent metadata, sorted output, and change-sensitive IDs.
- [ ] Run `PYTHONPATH=src .venv/bin/python -m unittest tests.test_chunking -v`;
  expect missing API failures before implementation.
- [ ] Implement small pure functions and validators; no tokenizer dependency.
- [ ] Run the full unittest suite; expect all original 55 and character checks green.
- [ ] Record evidence in ledger; do not commit.

## Task 2: Optional local-tokenizer chunk profile

**Files:** Create `src/research_pipeline/tokenization.py`,
`requirements-tokenizers.txt`, `tests/test_tokenization.py`;
extend `chunking.py`.

**Interfaces:** Produces `LocalTokenizer.from_file(path, model_id, revision)`
with `offsets(text)`, `counts(text)` and `provenance()` for Task 1's tokenizer mode.

- [ ] Write tests with a real tiny WordPiece tokenizer saved locally: disabled
  truncation, exact Unicode slicing, special tokens, impossible budgets, sparse
  token offsets, zero overlap and maximal overlap progress.
- [ ] Observe tokenizer-mode failure on Task 1 implementation.
- [ ] Add lazy optional dependency and local-only loader; pin tokenizers 0.23.2.
- [ ] Run all tests with optional dependency installed; also verify core tests
  with tokenizer dependency absent using Python -S for stdlib components.
- [ ] Record synthetic-vs-real-model validation distinction; no commit.

## Task 3: Generation publication and validated passage loading

**Files:** Create `src/research_pipeline/datasets.py`,
`tests/test_datasets.py`; extend fixtures.

**Interfaces:** `publish_dataset(staging, run_root, pointer_path)` atomically
selects a complete generation; `load_active_dataset(run_root, pointer_path)`
returns validated papers/pages/chunks/manifest; `load_passages(..., paper_ids=None)`
provides a model-independent handoff. Manifest schema version 1 lists exactly
papers.jsonl, pages.jsonl, chunks.jsonl and quality_report.json with hashes/counts.

- [ ] Write real-filesystem tests for round trips, repeated reuse, corrupt hashes,
  unsupported/incomplete schemas, semantically wrong metadata/offsets/IDs even
  with recomputed hashes, path traversal/symlink escapes, and missing exclusions.
- [ ] Seed a prior generation; inject directory/pointer replacement failures and
  verify prior pointer/artifact bytes remain unchanged.
- [ ] Observe missing publisher/loader failures, then implement immutable generations
  with one atomic pointer replacement; no sequential artifact replacements.
- [ ] Run full suite and record evidence; no commit.

## Task 4: Runner, standalone CLI and corpus handoff

**Files:** Create `src/research_pipeline/pipeline.py`, `cli.py`,
`chunking_cli.py`, `handoff.py`, `tests/test_pipeline.py`, `tests/test_pr3_cli.py`,
`tests/test_handoff.py`.

**Interfaces:** `run_pipeline(config, chunking, run_root, pointer_path,
allow_partial=False, tokenizer=None)` consumes PR1 ingestion/PR2 extraction.
`run_chunking(...)` consumes existing pages and the manifest. Commands support
`run`, `chunk`, `inspect`, and `coverage --metadata-csv PATH`, with explicit
paths/profile/settings. Coverage is read-only and keys on canonical versioned IDs.

- [ ] Write tiny real-PDF success/failure/partial tests and tests for source
  mutation, input/output aliases, default offline execution, CLI exit codes,
  blank pages, malformed pages, incomplete corpus, and unchanged PR1/PR2 files.
- [ ] Observe missing runner/CLI failures; implement by calling existing low-level
  stages only with scratch paths, recording actual hashes, and publishing after
  all validation. Stable stored diagnostics omit machine-specific paths.
- [ ] Test CSV duplicates/missing columns/noncanonical IDs and empty/no overlap.
- [ ] Run full suite; no commit.

## Task 5: Corpus verification, docs and independent final review

**Files:** Update README, docs/pipeline.md; create docs/pr3_validation.md,
docs/pr3_draft_description.md, docs/chunking_evaluation_plan.md,
`tests/validate_pr3_corpus.py`.

**Interfaces:** Validator runs the real five-paper fixture against active data,
checking source PDF hashes, all 104 pages, exact chunk reconstruction, complete
coverage, deterministic artifact hashes, and no default network access.

- [ ] Execute all profiles offline (real local tokenizer fixture for tokenizer
  mode); clearly separate synthetic tokenizer evidence from actual MiniLM assets.
- [ ] Repeat runs and compare every stored artifact; validate legacy CLI regression.
- [ ] Run all tests, compileall, pip check and whitespace/secret/path scans.
- [ ] Document future Recall@5/MRR/citation correctness/latency comparison with
  fixed corpus/model/settings, deduplicated evidence and held-out questions.
- [ ] Have one fresh reviewer inspect the entire uncommitted diff; fix important
  findings with RED-to-GREEN tests and re-run the full suite.
- [ ] Report implemented scope, passed checks, unverified integration/model
  experiments and review readiness. Keep every change uncommitted and local.
