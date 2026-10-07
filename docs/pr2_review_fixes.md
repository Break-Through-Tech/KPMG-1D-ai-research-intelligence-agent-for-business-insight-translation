# PR 2 audit corrections and validation

## Summary and scope

These corrections harden the shared PR 1 ingestion contracts and PR 2 PDF
extraction while keeping the existing five-paper, local-only prototype. No
chunking, retrieval, embeddings, generation, UI, or Team 1F material is included.
The changes build on PR 2 head `a21722c84277ab8049273a3ae64a5e8566459aec`.
The user approved committing and updating the existing PR after this validation;
merging remains a separate approval step.

## Why these changes exist

The audit found a vulnerable parser pin, incorrect citation URLs passing
validation, interrupted downloads that could be skipped on retry, multiple paper
identities sharing one source PDF, and three smaller contract/cleanup defects.
Normal fixture runs passing did not cover those failure modes.

## Corrections

| Finding | Correction | Regression evidence |
|---|---|---|
| Vulnerable PDF parser pin | Upgrade to `pypdf[fonts]==6.19.0`; pin `fonttools==4.66.1` for the corpus's CFF fonts. | Full suite, real-corpus comparison, dependency checks; no hostile payload was run. |
| PDF URL not bound to identity | Require the exact versioned paper in the arXiv PDF path; optional `.pdf` suffix remains valid. | Wrong papers/versions, versionless/bare paths, extraneous URL components and Atom mismatches are rejected. |
| Interrupted downloads poison retries | Write complete bytes into a temporary sibling, close, then replace. | Injected disk-full and PDF-replacement failures preserve destinations and remove failed temporaries; reruns download successfully. |
| Papers sharing a source | Reject lexical/resolved path collisions and existing device/inode aliases on load/save/collection; stages pass their root. | Load/save and both CLIs reject shared paths; new collection cannot claim an existing path. Case-only, symlink and hardlink checks pass. |
| Identifier casing breaks idempotence | Reject noncanonical IDs before collection or manifest loading. | Uppercase version/category variants fail before requests or manifest changes. Canonical modern/legacy reruns still work. |
| Failed storage leaves temporaries | Clean JSON/JSONL temporaries in `finally`, including iterator/serialization/replacement errors. | Previous bytes remain intact and no failed temporary files remain in the tested cases. |
| Dates less strict than documented | Require the canonical calendar-date representation. | Compact/week dates and invalid calendar dates are rejected; a valid leap day is accepted. |

An independent read-only review reproduced a case-only filename alias missed by
the initial path-spelling fix. Its additional file-identity correction was
verified with failing case/hardlink tests followed by a passing full suite.
The reviewer also flagged stale documentation, which is updated here.

## Methodology and results

Behavioral regression tests were run against the unfixed behavior before the
corresponding changes, then passed after correction. Existing output preservation,
partial-publication, blank-page and failure-reporting contracts remain in place.

- 55 offline tests passed; no tests skipped on this Mac.
- 27 ingestion/metadata/storage/download tests passed with `python -S`, without
  site packages.
- The exact merged PR 1 baseline independently passed 13 tests and local
  ingestion: all five PDFs available, exit 0.
- The unchanged, separate three-stage prototype passed its 42 tests as a
  reference only; its future modules are not included in this PR.
- Both corrected local CLIs returned success, exit 0: five papers, 104 original
  pages, 373,976 cleaned characters.
- No missing, parsing-failed, no-text or empty fixture pages/papers.
- Every citation field matched its manifest; every original page sequence was
  contiguous and matched the physical PDF page count. All paper/page keys were
  unique and JSONL/model round trips were lossless.
- Titles and all listed authors were found in the first two extracted pages of
  their corresponding PDFs. This is an identity spot-check, not full semantic
  validation of every PDF element.
- Supplied PDF blob hashes still match the pre-PR baseline; no PDFs were changed.
- Repeated full runs produced byte-identical catalog and page outputs.
- A guard on the default network entry point observed no requests.
- Injected final filesystem replacement failures in both CLIs returned 3,
  preserved prior artifact bytes and cleaned staging.
- `compileall`, `pip check` and whitespace validation passed. `pip check` measures
  dependency consistency, not vulnerability absence.
- Public OSV lookups for the two pinned package names/versions returned no known
  vulnerabilities at the time of validation. This is a dated database result,
  not a guarantee of safety. The lookup sent no project or paper contents.
- A scan of project text for common secret/private-key formats and user-specific
  absolute paths found no matches. Credential and generated-data paths remain
  ignored and untracked. This scan does not prove all possible secrets absent.

## Explicit extraction rebaseline

The old 6.1.1 run produced 373,982 characters. The patched run produces 373,976.
Of the 104 pages, 47 have identical text and 56 differ only in whitespace. The
remaining page, `2608.20316v1` physical page 19, changes a misdecoded summation
glyph from U+00CD to U+02DD. Visual inspection shows the source uses a summation
symbol; neither extracted form is correct. No paper-specific text substitutions
were added. The original PDF remains authoritative for equations.

The six-character net decrease does not mean only six characters changed:
spacing and line-break placement differ across many pages. Paper citations,
page positions, paper count and page count remain identical. Installing the
font decoder removes the missing-font warnings but does not correct this glyph.

Reproducible hashes with the new pinned dependencies:

```text
papers.jsonl f51899b772dd2ae3844844c6b62a9f09e2b2a02e6c2e1c98770531e8065859ce
pages.jsonl  afb19df94fc17cd4e369bf0a07e4e6f9be0c2682043c708f1f80e5bc0e5a7e1a
```

## Files changed by this correction

- `requirements.txt`: patched parser and reproducible font-decoder pins.
- `src/research_pipeline/models.py`: citation, ID and date validation.
- `src/research_pipeline/ingestion.py`: source uniqueness and atomic downloads.
- `src/research_pipeline/extraction.py`: supplies the configured source root.
- `src/research_pipeline/storage.py`: atomic binary writer and failure cleanup.
- Four focused regression files: metadata, manifest paths, storage, downloads.
- `README.md`, `docs/pipeline.md`, and this report: contracts and verified results.

## Exact validation checklist

Run from the repository root with the dependencies installed:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
PYTHONPATH=src .venv/bin/python -S -m unittest \
  tests.test_ingestion tests.test_metadata tests.test_storage \
  tests.test_collection_hardening -v
PYTHONPATH=src .venv/bin/python -m research_pipeline.ingestion_cli ingest
PYTHONPATH=src .venv/bin/python -m research_pipeline.extraction_cli
shasum -a 256 data/processed/papers.jsonl data/processed/pages.jsonl
PYTHONPATH=src .venv/bin/python -m research_pipeline.ingestion_cli ingest
PYTHONPATH=src .venv/bin/python -m research_pipeline.extraction_cli
shasum -a 256 data/processed/papers.jsonl data/processed/pages.jsonl
PYTHONPATH=src .venv/bin/python -m compileall -q src tests
.venv/bin/python -m pip --no-cache-dir check
git diff --check
```

## Remaining limitations and risks

PDF text can still distort equations, tables, figures, column order or glyphs.
Scanned content needs OCR. Nonempty existing downloads are availability checks,
not full PDF parse/identity verification. Atomic writes do not provide power-loss
durability, concurrent-writer coordination or guaranteed cleanup after abrupt
termination. Root-aware alias checks do not create a filesystem security sandbox.
Live arXiv behavior, retrieval integration and answer quality remain untested.
Current validation is local; the existing PR does not list automated GitHub checks.

No secret disclosure or evaluation leakage was identified in the reviewed code,
but this is not a universal data-security guarantee. Later indexing must exclude
benchmark answers/labels and evaluation reports, and research text must be treated
as data rather than instructions.

## Dependency sources

- [pypdf maintainer advisory](https://github.com/py-pdf/pypdf/security/advisories/GHSA-jw7q-gvrg-4vj3).
- [pypdf 6.19.0 release](https://github.com/py-pdf/pypdf/releases/tag/6.19.0).
- [fonttools 4.66.1 release](https://github.com/fonttools/fonttools/releases/tag/4.66.1).
- [OSV version-query API](https://google.github.io/osv.dev/post-v1-query/).
