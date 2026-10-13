# PR3: Citation-preserving chunks and a reproducible data runner

Date: October 7, 2026

Status: Approved for local implementation, including the user's seven refinements.
This document is local and uncommitted. It does not authorize a push or PR.

## Purpose and boundaries

Prepare research passages for Task #1, embedding/vector-search prototyping,
without replacing Matias's paper-level retrieval or implementing an unrelated
search system. The original project remains source-grounded research retrieval,
summarization, and business interpretation for human review.

PR3 delivers chunking, reproducible artifact provenance, safe combined data
publication, a validated passage loader, and documentation. Embedding inference,
Chroma indexing, model comparison, BM25, hybrid retrieval, reranking, generation,
and a UI remain separate follow-up work. Tokenization is not embedding inference.

Team 1F architecture, approaches, engineering decisions, and reported results
may inform learning and comparison. Team 1D implementation, tests, comments,
and documentation must be independently developed to fit our existing contracts,
not copied or cosmetically renamed from Team 1F. Learning from their work is
permitted; simply copying their code or documentation is not.

## Baseline and local-work constraints

- Start implementation from merged main commit
  `2712b797a31b219060abf83e8a7637475b39c606`, which includes PRs #9 and #10.
- Preserve the existing dirty original checkout and its earlier three-stage
  prototype. Do not reset it, overwrite its generated data, or cherry-pick the
  old prototype wholesale over the hardened merged contracts.
- Implementation will use an isolated Team 1D checkout. The current working
  directory may be Team 1F; all operations must explicitly target Team 1D.
- Keep all work local. Do not commit, push, create/update a GitHub PR, modify
  GitHub issues, or message another task/team without separate user approval.
- Python 3.11 or newer; retain the merged PDF dependencies and the
  standard-library-only ingestion boundary. Optional tokenizer dependencies
  must be separate from the ordinary ingestion/extraction requirements.
- Respect Shah's style: readable functions, descriptive names, clear contracts,
  small modules, useful public docstrings, explanatory comments, pathlib,
  meaningful offline tests, and reproducible result documentation.

## Inputs and validation

Use the existing `PaperMetadata` and `ExtractedPage` contracts. Page numbers are
positive, 1-based physical PDF positions, not printed labels. Blank pages remain
page records and produce no chunks.

Before chunking, validate every record, reject duplicate `(paper_id,
page_number)` keys, and check that citation metadata agrees across a paper's
pages and with its manifest. Within each included paper, page positions must be
contiguous from 1. Sort valid inputs by paper ID and page number to make output
independent of input-line order. A structural validation error is failure, not
an explicitly publishable partial corpus.

Coverage validation distinguishes requested papers from included usable papers.
In the combined runner, the extraction report provides missing, failed, and
no-text paper identities. A standalone chunk operation compares supplied page
identities with the manifest and reports missing papers; page continuity alone
cannot prove that the final page was not omitted. Its provenance records that
it consumed existing page JSONL rather than reparsing PDFs.

Inputs, outputs, staging locations, and pointer paths must not alias each other
or a tracked source PDF. Reject configurations that would overwrite an input.

## Chunking profiles

Three explicit profiles share one citation contract:

1. `boundary_characters`: the ordinary offline default. Maximum 1,800 Unicode
   characters, target overlap 200 characters. Prefer paragraph boundaries, then
   sentence boundaries, then whitespace; fall back to a hard character boundary
   for an oversized unbroken segment. This is boundary-aware chunking, not
   embedding-based semantic chunking.
2. `fixed_characters`: the original 1,800-character, 200-character-overlap
   baseline, retained for controlled comparisons and allowed to split words.
3. `tokenizer`: optional model-specific token-budgeted chunking using an
   explicitly supplied local Hugging Face fast-tokenizer JSON and its declared
   model ID/revision. The initial MiniLM profile targets at most 200 content
   tokens and approximately 40 content tokens of overlap, with an actual
   complete-input ceiling of 256 tokens, including special tokens. The embedding
   text template is the chunk text alone; titles/prefixes are not silently added.

Token counts use the actual selected tokenizer, never a characters-per-token
estimate. Tokenizer token IDs are not decoded to reconstruct source text;
offsets identify exact substrings of the cleaned page, preserving case and
Unicode. Recheck each final substring with truncation and padding disabled,
including special-token processing. If the tokenizer configuration contains
active truncation, disable it for counting so an overlong input cannot appear
valid. Token settings or tokenizer failures must fail clearly rather than
silently falling back to character chunking.

The optional mode loads only local tokenizer assets. It must not fetch model
weights, contact a hosted API, or download assets automatically. Offline tests
use a tiny locally constructed tokenizer fixture plus injected counters where
appropriate; a separately labelled real-tokenizer check is required before
claiming compatibility with MiniLM. Without that check, reports explicitly say
the real model/tokenizer was not validated.

For both character profiles, use half-open windows `[start, end)`. A non-final
window must exceed the overlap; the next start is exactly `end - overlap`.
Boundary-aware ends are the last preferred boundary within the hard budget
that also permits progress, otherwise the hard end is used. Consequently both
character profiles overlap by exactly the configured character count; an
overlap-start may be inside a word even when the end prefers a word boundary.

For tokenizer mode, choose an end using actual content-token offsets, verify
the final substring against both budgets, and shorten if necessary. The next
start is the start offset of the last N content tokens of that substring,
clamped to at least `previous_start + 1`; with zero overlap it is exactly the
previous end. If fewer than N tokens fit, the clamp still guarantees progress.
Retokenization and normalization mean this is an offset-defined overlap, not
a promise of exactly N tokens after encoding the next substring.

All profiles must advance on every iteration, stay inside one page, respect
their selected budget, and cover every Unicode source character without gaps
on a nonblank page. Empty strings are never chunks. All-whitespace pages are
retained as pages and explicitly skipped; whitespace-only windows inside a
nonblank page are retained to preserve full coverage and counted in reports.
Future embedding adapters may skip those windows explicitly. Boundary preference
must never create an infinite loop or violate coverage. A single Unicode
character that cannot fit a token budget is a clear failure. Offsets count
Python Unicode code points, including combining marks, never UTF-8 bytes.

Character-mode outputs report token counts as unknown, not zero, and do not
claim that they fit every embedding model. An embedding-stage length check
remains mandatory when those outputs are used later.

## Passage contract and identifiers

One UTF-8 JSONL record represents one contiguous passage on one cleaned page.
Required fields:

- `schema_version`: `1`.
- `chunk_id`: deterministic content-sensitive identifier.
- `paper_id`, `paper_version`, `title`, ordered `authors`, `published`, `pdf_url`:
  unchanged citation fields from the validated page record.
- `page_number`: original physical PDF position.
- `start_character`, `end_character`: zero-based, half-open Unicode character
  offsets into the cleaned page text; not byte offsets or PDF coordinates.
- `text`: exactly `page.text[start_character:end_character]`.
- `page_text_sha256`: SHA-256 of the cleaned page's UTF-8 text.
- `chunking_profile_sha256`: hash of canonical effective profile settings,
  algorithm version, and tokenizer identity/asset hash when applicable.
- `content_token_count`: actual content count for tokenizer mode, otherwise null.
- `input_token_count`: complete encoded-input count for tokenizer mode,
  otherwise null.

Build `chunk_id` from a readable paper/page prefix and a full SHA-256 digest of
all citation identity fields, source text hash, offsets, chunk text, and profile
hash.
Identical input/configuration produces identical IDs; changed content or
configuration cannot silently retain the same ID. Duplicate IDs are rejected.

Record parsing rejects non-object values, missing fields, booleans where integers
are required, invalid ranges, empty text, and malformed hashes. Source offsets
and text are additionally verified against the loaded page before publication.

A small passage loader exposes validated chunks and optional paper-ID filtering
without depending on a vector database. It preserves authors as an ordered list;
future Chroma-specific metadata serialization belongs to the indexing adapter.

## Provenance and reports

Each complete candidate run contains `papers.jsonl`, `pages.jsonl`,
`chunks.jsonl`, `quality_report.json`, and `run_manifest.json`.

The run manifest records schema/algorithm versions, canonical effective
configuration, manifest/input hashes, source PDF hashes when the combined
runner actually reads PDFs, tokenizer asset/model/revision when applicable,
parser dependency versions, requested/included/excluded paper IDs, and artifact
hashes/counts. Artifact hashes in the manifest cover the four other artifacts,
not the manifest itself; its hash belongs in the active pointer. The manifest
must not invent PDF hashes for a standalone page-input run. Hash the actual
consumed input bytes and fail if a source changes during processing.

Reports include outcome, coverage, blank pages, missing/failed/no-text papers,
chunk counts per paper, size summaries, unique IDs, provenance validation, and
storage round-trip results. A zero-chunk corpus is failure with round-trip state
null. Counts establish preparation, not semantic search or answer quality.

Canonical stored data and reports exclude wall-clock timestamps and machine-
specific absolute paths so identical inputs produce byte-identical artifacts.
Temporary directory names are never embedded in the dataset. A runtime CLI
message may print a resolved output location for user convenience.

## Publication and compatibility

Existing PR1 ingestion and PR2 extraction CLIs retain their paths and single-file
publication behavior. The new combined runner must not repurpose their shared
helper to sequentially replace multiple public artifacts.

Use a separate ignored run root, `data/processed/runs/`. Stage a complete
candidate generation on the same filesystem, validate all records/readbacks and
artifact hashes, then publish an immutable generation directory. Switch the
single `data/processed/active_run.json` pointer with atomic single-file
replacement only after that directory is complete. The pointer contains a
validated relative generation path and run-manifest hash. Reject traversal,
absolute paths, and symlink escapes outside the configured run root. Loaders
resolve all artifacts through the same selected generation and verify the
manifest and artifact hashes, never a mixture of generations. Reject unsupported
schema versions, missing artifact entries, inconsistent paper/page/chunk metadata,
invalid offsets/IDs, unaccounted corpus exclusions, and incomplete manifests.
Reconstruct every chunk by slicing its cited cleaned page and require exact
equality. Hash validation alone is not sufficient semantic validation.

The standalone chunking command publishes an equivalent generation using the
supplied catalog/page inputs; it does not modify those source files. It may
materialize a validated catalog from the manifest if no catalog is supplied.
The CLI must explain that generated passages are discovered through the active
run rather than silently writing a stale legacy `chunks.jsonl` path.

Derive the generation ID from the completed run-manifest hash. Do not include
the generation ID or its filesystem path inside that manifest, avoiding a
circular hash dependency. A byte-identical existing generation can be reused
only after hash
verification; a conflicting existing directory is failure and is not overwritten.
Filesystem or pointer-switch failures preserve the previous active pointer and
its dataset. A completed but unreferenced generation may remain after an
interruption; no automatic deletion of historical runs is in scope.

Outcome codes remain success 0, usable partial failure 2, and failure 3. Default
partial/failed runs do not switch the pointer. `--allow-partial` may publish a
usable incomplete candidate, still returns 2, and lists excluded papers in the
manifest/report. Empty or structurally invalid candidates never publish.

The final printed `artifacts_published` flag becomes true only after the pointer
replacement succeeds. Stored quality reports describe the candidate dataset;
they must not predeclare a successful publication before it occurs.

This is a local, single-writer prototype. Atomic replacement prevents readers
from seeing a mixed generation; it is not a power-loss durability guarantee,
multi-writer lock protocol, or production filesystem security boundary.

## Retrieval handoff and Task #1

Matias's inspected `Retrieval_Indexing` branch uses MiniLM and Chroma to search
titles/abstracts for ten September papers. Its second-stage passage search is a
proposal, not implemented integration. Our fixed five papers have different
IDs; matching the identifier format does not establish corpus overlap.

PR3 documents this mismatch and provides a read-only optional CSV coverage check
using the existing `id` column. It reports shared IDs, IDs only in the page
corpus, and IDs only in the CSV without editing either dataset or fabricating
abstracts/categories. It does not require Matias's branch files to exist.

Before two-stage retrieval, the team must choose a common corpus and agree on
who owns passage indexing and evaluation. Initially, independently test passage
retrieval over the five-paper fixture rather than filter it using unrelated
paper candidates.

The next experiment compares MiniLM dense retrieval with BGE-M3 dense retrieval
on the same passage texts and agreed questions, with explicit input-length
validation for each tokenizer and separate model-specific indexes. Larger
BGE-specific chunks, BM25, hybrid fusion, and reranking are separate experiments,
not simultaneous changes to the baseline. Similarity/distance is not calibrated
confidence. Benchmark questions and relevance labels must remain outside the
indexed corpus; reserve held-out questions before tuning. Five papers provide a
small engineering baseline, not evidence of broad business usefulness.

Document a later controlled comparison of the three chunking profiles using
the same corpus, embedding model/revision, retrieval settings, and frozen
questions. Relevance annotations should identify supporting paper/page/source
spans, not one profile's chunk IDs. Report Recall@5, MRR, citation reconstruction
and support correctness, and query latency with an explicit timing boundary.
Overlapping chunks covering the same evidence should not inflate Recall@5.
Separate indexing time from query latency and separate development from held-out
questions. This is documentation only; PR3 implements no retrieval evaluation.

## Verification and documentation requirements

Re-run the merged 55-test suite before and after changes. Add targeted offline
tests for all three chunking profiles, Unicode and long unbroken inputs, boundary
progress, blank pages, overlap/coverage, duplicate/malformed/non-object pages,
conflicting citation metadata, exact offsets, token overhead/truncation, invalid
budgets, deterministic/change-sensitive IDs, loader filtering, CSV coverage,
round trips, and input/output alias rejection.

Publication tests seed a previous active generation and exercise every failure
stage: ingestion, extraction, chunking, serialization, directory publication,
and pointer replacement. Assert its pointer bytes and artifact hashes remain
unchanged. Test explicit partial publication separately and verify exit code 2.

Validate the five real PDFs with the patched parser, all 104 physical pages,
source metadata, chunk/page substring linkage, unchanged PDF hashes, identical
reruns, and a network guard for default processing/tests. Do not hard-code the
old 271-chunk expectation for changed chunking. Tokenizer-mode corpus validation
must be explicitly separated from ordinary character-mode checks if the real
tokenizer is not locally available.

Run compileall, dependency checks, diff whitespace checks, and reviewed
secret/local-path scans. Update README, the pipeline guide, a PR3 validation
report, and a local draft PR description with actual commands/results, scope,
limitations, publication paths, corpus mismatch, and tokenizer availability.
No test count, model compatibility, or retrieval performance may be claimed
until observed.

## Approval checkpoints

The user approved the design with these refinements and explicitly requested
direct implementation without further approval pauses. Prepare a local plan,
execute natively in this chat, verify and fix findings, and report evidence.
Commit/push/PR actions still require separate explicit user approval.
