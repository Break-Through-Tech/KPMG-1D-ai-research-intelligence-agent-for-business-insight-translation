# Reproducible ingestion and citation-preserving page extraction

Stage 1 defines the prototype corpus, validates metadata, and prepares a paper
catalog. Stage 2 extracts each original PDF page with source citation metadata.
Both use the five supplied PDFs as a fixed local fixture; neither builds a
retriever or chunks text.

## Setup and local commands

Use Python 3.11 or newer. Ingestion is standard-library-only. Extraction needs
the pinned pypdf dependency; tests include tiny real PDFs generated offline.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
PYTHONPATH=src python -m research_pipeline.ingestion_cli ingest
PYTHONPATH=src python -m research_pipeline.extraction_cli
PYTHONPATH=src python -m unittest discover -s tests -v
```

The default command requires no network. It reads `data/manifest/papers.json`,
validates records, checks local PDF availability, and stages the catalog before
replacing `data/processed/papers.jsonl`. The catalog contains one paper per line
and is generated rather than committed. Reruns do not append duplicate records.

The five supplied PDFs remain tracked at their existing `data/` paths. Newly
downloaded PDFs go under ignored `data/raw/pdfs/`. Environments, generated
catalogs, vector databases, and local secrets are also ignored.

A different manifest can be passed before the subcommand:

```bash
PYTHONPATH=src python -m research_pipeline.ingestion_cli \
  --manifest data/manifest/another-corpus.json ingest
```

## Paper metadata contract

The manifest is a JSON list; the generated catalog is UTF-8 JSONL. Both use the
same required fields. Missing or blank metadata is rejected.

| Field | Meaning and validation |
|---|---|
| `paper_id` | Unique canonical versioned arXiv short ID, such as `2608.20316v1` or `hep-th/9901001v1`; lowercase `v` and a positive version are required. |
| `paper_version` | `vN` suffix matching `paper_id`. |
| `title` | Non-empty paper title. |
| `authors` | Non-empty ordered list of non-empty author names. |
| `published` | ISO publication date in `YYYY-MM-DD` form. |
| `pdf_url` | HTTP(S) arXiv PDF URL identifying exactly the same paper and version; optional `.pdf` suffix is accepted, queries/fragments are rejected. |
| `source_path` | Unique repository-relative PDF path; absolute paths and `..` are rejected, as are paths sharing a PDF with another identity. |

Versioned identifiers avoid silently switching to a later revision. The
manifest fixture records the supplied papers' identities, titles, authors, and
dates; the catalog preserves those fields. Existence and nonzero file size are
availability checks, not proof that a PDF parses or its text is usable. Those
checks belong to the extraction stage described below.

Noncanonical dates such as `20260821` and `2026-W34-5` are rejected. IDs with
uppercase version suffixes are rejected before collection, rather than silently
changing identifiers or creating differently keyed duplicates. Legacy category
prefixes use lowercase names with uppercase subject suffixes when present
(for example `cs.LG/9901001v1`).

Manifest loading and saving reject normalized duplicate paths. All pipeline
stages provide their repository root so validation also resolves symlinks and
checks device/inode identity for existing hardlinks and case-only filename
aliases. A newly collected record is checked before its PDF is downloaded.
This protects attribution; it is not a semantic proof that an arbitrary PDF
contains the declared paper. `load_manifest` and `save_manifest` callers must
also provide their root to request these existing-file alias checks.

## Optional explicit arXiv collection

Collection makes live requests only when the `collect` command is used. Choose
paper IDs explicitly; the implementation does not search the latest category
feed or run on a schedule.

```bash
# Metadata only; an existing manifest entry is skipped without a request.
PYTHONPATH=src python -m research_pipeline.ingestion_cli collect \
  --arxiv-id 2608.20316v1

# Optional PDF download for the selected version.
PYTHONPATH=src python -m research_pipeline.ingestion_cli collect \
  --arxiv-id 2608.20316v1 --download-pdf
```

Metadata comes from `https://export.arxiv.org/api/query`; PDF links come from
the Atom response. IDs must include a version. The CLI prints the live source
and requested count. Modern and legacy identifiers preserve their complete
`/abs/` path, including category prefixes and nested local PDF paths.

Metadata request attempts run sequentially and start at least three seconds
apart, including failed attempts, following [arXiv's API rate
limits](https://info.arxiv.org/help/api/tou.html#rate-limits). Existing metadata
and non-empty local PDF files are skipped. Downloads must begin with a PDF
header, but full parsing is deferred. Successful metadata is saved even if an
optional PDF download fails, allowing a later retry without losing the record.
PDF bytes are written to a temporary sibling and replace the final path only
after a complete successful write and close. Failed writes/replacements preserve
the previous destination and clean temporary files when the filesystem permits.
They cannot leave a newly truncated final PDF that a rerun mistakes for a download.

## Outcomes and output preservation

| Outcome | Exit code | Behavior |
|---|---:|---|
| `success` | 0 | The requested operation completed. Local ingestion publishes its catalog only when every manifest PDF is available. |
| `partial_failure` | 2 | Some records/files succeeded and others failed. Local ingestion preserves the previous catalog. |
| `failure` | 3 | No local PDFs are available, all metadata requests fail, or validation prevents the command from running. |

Metadata-only collection can succeed without local PDFs because it did not
request them. Any failed metadata request or requested PDF download makes
collection return nonzero. Per-paper failures appear in the printed report.
Catalog publication uses a staged file and replaces its destination after
validation. This is a single-file operation in this stage.
JSON/JSONL helpers also clean temporary files after serialization, iterator, or
replacement errors. Atomic replacement is not a power-failure durability or
concurrent-writer guarantee; abrupt process termination can leave temporary files.

## Page extraction and cleanup

The independent extraction command reads the same validated manifest directly;
it does not depend on a previously generated catalog or any later-stage module.
PDF parsing uses `pypdf[fonts]==6.19.0` and `fonttools==4.66.1`, with `strict=False`
to tolerate nonfatal PDF format irregularities. The font extra supports embedded
CFF fonts in the supplied PDFs. It calls text extraction separately on every page.

The previous `pypdf==6.1.1` pin was below the maintainer's patched version for
[malformed-stream resource exhaustion](https://github.com/py-pdf/pypdf/security/advisories/GHSA-jw7q-gvrg-4vj3).
Upgrading reduces known dependency risk; it does not sandbox arbitrary PDFs or
establish production security.

Cleanup removes NUL characters, normalizes line endings and nonbreaking spaces,
collapses horizontal whitespace, trims lines, and limits consecutive blank
lines. It does not remove repeated headers/references, merge hyphenated words,
reorder columns, reconstruct tables, or infer missing equations.

`data/processed/pages.jsonl` is UTF-8 JSONL with one record per original PDF page:

| Field | Meaning |
|---|---|
| `paper_id`, `paper_version` | Versioned paper identity from the manifest. |
| `title`, `authors`, `published`, `pdf_url` | The same validated citation metadata as the paper catalog. |
| `page_number` | Positive integer, 1-based physical PDF position; not the printed page label. Boolean values are rejected. |
| `text` | Conservatively cleaned string; blank pages deliberately retain `""`. |

Blank pages preserve citation positions. If any page of a paper fails to parse,
all pages from that paper are discarded and its error is reported; other papers
continue. Missing/zero-byte files appear in `missing_pdfs`. Parsed blank or
zero-page papers appear in `papers_without_usable_text` and do not count as
`papers_succeeded`.

The CLI prints counts, usable/empty pages, original blank-page positions,
missing/failed/no-text papers, cleaned character count, outcome, and
`artifacts_published`. The report is printed, not stored as a quality-report
artifact in this stage. Character counts are Python string lengths, not tokens.

## Extraction outcomes and preservation

| Outcome | Exit code | Publication |
|---|---:|---|
| `success` | 0 | Every requested paper has at least one nonempty cleaned page; publish the page file. Blank pages within usable papers are allowed. |
| `partial_failure` | 2 | Some usable papers, but at least one missing/failed/no-text paper. Preserve the previous page file by default. |
| `failure` | 3 | Empty corpus, no usable text, or validation/filesystem failure. Do not publish. |

`PYTHONPATH=src python -m research_pipeline.extraction_cli --allow-partial`
explicitly publishes usable partial results, including blank-page records.
It still returns 2; it never publishes a total failure. Without this flag,
previous page output is preserved byte-for-byte after partial/failed runs.

`extraction_cli.run_extract` is the safe programmatic entry point. The lower-level
`extraction.extract_manifest_pages` writes its configured output even for a
partial or failed corpus; use it only with a scratch/staged path. The wrapper
stages the page file and uses the existing PR 1 single-file replacement helper.
It leaves the ingestion catalog untouched and cleans staging on completion.

## Validation and observed results

The merged PR 1 baseline was revalidated before adding extraction:

- 13 offline tests passed.
- The manifest contained 5 papers, and all 5 PDFs were available.
- Ingestion returned `success`, exit code 0.
- Repeated catalog generation produced identical bytes.

The commands above then ran in a fresh virtual environment in an isolated
checkout containing PRs 1–2 only (no chunking, combined CLI, or runner):

- All 55 offline tests passed: the original 32 ingestion/extraction checks plus
  23 citation-contract, path-alias, atomic-download, and storage regressions.
- The 27 ingestion/metadata/storage/download tests also passed with Python's
  `-S` flag, without site packages, confirming standard-library ingestion.
- Both ingestion and extraction returned `success`, exit code 0.
- All 5 PDFs parsed: 104 pages and 373,976 cleaned characters.
- Zero missing PDFs, parsing failures, no-text papers, or empty pages.
- Every stored citation field matched its manifest paper; all page sequences
  were contiguous from 1, and JSONL/model round trips preserved records.
- Repeated ingestion/extraction runs produced identical SHA-256 hashes.
- Source PDF Git blob hashes matched merged main; no PDFs were changed.
- `python -m compileall -q src tests`, `python -m pip --no-cache-dir check`,
  and `git diff --check` passed.

| Paper ID | Extracted pages |
|---|---:|
| `2608.20316v1` | 28 |
| `2608.20318v1` | 19 |
| `2608.20319v1` | 23 |
| `2608.20320v1` | 25 |
| `2608.20331v1` | 9 |

Repeated output SHA-256 values:

```text
papers.jsonl f51899b772dd2ae3844844c6b62a9f09e2b2a02e6c2e1c98770531e8065859ce
pages.jsonl  afb19df94fc17cd4e369bf0a07e4e6f9be0c2682043c708f1f80e5bc0e5a7e1a
```

To reproduce the byte comparison, hash both files, rerun both stage commands,
and hash them again:

```bash
shasum -a 256 data/processed/papers.jsonl data/processed/pages.jsonl
PYTHONPATH=src python -m research_pipeline.ingestion_cli ingest
PYTHONPATH=src python -m research_pipeline.extraction_cli
shasum -a 256 data/processed/papers.jsonl data/processed/pages.jsonl
python -m compileall -q src tests
python -m pip --no-cache-dir check
git diff --check
```

Offline fixtures cover duplicate/invalid metadata, missing files, reruns,
download failures, modern and legacy IDs, mismatched/malformed Atom responses,
and pacing through injected clock/sleep functions. Tests require no API key,
model download, network, or real sleeping. Live collection has not been tested
against arXiv as part of this validation.

Extraction fixtures cover conservative cleanup, blank-page positions, zero-page
PDFs, mixed usable/no-text papers, partial/total missing and parsing failures,
later-page failure without leaked partial pages, malformed metadata and
non-object manifest records, empty
corpora, prior-output preservation, explicit partial publication, cleanup of
staging, unchanged catalogs, citation round trips, and exit codes 0/2/3.

The original local three-stage prototype's 42 tests were also re-run and passed
as a separate reference check. Those future-stage modules and tests are not in
PR 2, and the original folder's outputs were not replaced. Their extraction and
chunk baselines must be revalidated with the patched parser when PR 3 is built.
Preparation counts are not complete EDA or a measure of retrieval quality.

The patched parser's output was compared with 6.1.1 on all 104 pages: 47 pages
were identical, 56 differed only in whitespace, and one changed an equation
glyph on page 19 of `2608.20316v1`. Visual inspection confirmed that both versions
misdecode that summation glyph. The new total is six characters smaller overall,
but there are many layout changes, not merely six deletions. Citation metadata
and page identities are unchanged. See [the review-fix report](pr2_review_fixes.md)
for the explicit rebaseline and known limitations.

## Retrieval handoff and next stages

The versioned `paper_id` follows the `id` convention in Matias's
`Retrieval_Indexing` branch. That branch already downloads recent papers and
indexes titles and abstracts; it remains separate from this fixed-manifest
implementation. No CSV adapter or combined retrieval workflow is included.

A third PR will consume these pages and create chunks with source citation
metadata. Later integration should agree on the corpus
and bridge this manifest to Matias's CSV rather than maintaining two competing
paper collections. This stage does not collect abstracts or categories for his
index; those fields would need to come from his metadata or a future adapter.

## Limitations

PDF extraction can merge words, retain line-break hyphenation, misorder multiple
columns, and distort or lose figures, tables, equations, or glyphs. Scanned
image-only PDFs need OCR, which is not implemented. Sampling the supplied first
and last pages confirms title/body/reference/appendix text is present, not that
every PDF element is accurate. The original PDF remains authoritative.

There is no retry framework, scheduled collection, latest-paper search,
chunking, CSV adapter, passage index, embeddings, generation, UI, or retrieval
evaluation here. Identifier compatibility with Matias is not a tested retrieval
integration. These results establish data preparation, not research answer
quality.
