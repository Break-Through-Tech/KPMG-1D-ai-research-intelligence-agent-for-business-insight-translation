# Reproducible paper ingestion and metadata contracts

This first stage defines which papers belong to the prototype corpus, validates
their metadata, and prepares a catalog for later extraction. It uses the five
supplied PDFs as a fixed local fixture. It does not extract text or build a
retriever.

## Setup and local commands

Use Python 3.11 or newer. This stage has no third-party dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate
PYTHONPATH=src python -m research_pipeline.ingestion_cli ingest
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
| `paper_id` | Unique versioned arXiv short ID, such as `2608.20316v1` or `hep-th/9901001v1`. |
| `paper_version` | `vN` suffix matching `paper_id`. |
| `title` | Non-empty paper title. |
| `authors` | Non-empty ordered list of non-empty author names. |
| `published` | ISO publication date in `YYYY-MM-DD` form. |
| `pdf_url` | arXiv PDF URL for source attribution and optional download. |
| `source_path` | Repository-relative PDF path; absolute paths and `..` are rejected. |

Versioned identifiers avoid silently switching to a later revision. The
manifest fixture records the supplied papers' identities, titles, authors, and
dates; the catalog preserves those fields. Existence and nonzero file size are
availability checks, not proof that a PDF parses or its text is usable. Those
checks belong to the next extraction stage.

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

## Validation and observed results

The commands above were executed in an isolated checkout containing only this
stage:

- 13 offline tests passed.
- The manifest contained 5 papers, and all 5 PDFs were available.
- Ingestion returned `success`, exit code 0.
- Repeated catalog generation produced identical bytes.

Offline fixtures cover duplicate/invalid metadata, missing files, reruns,
download failures, modern and legacy IDs, mismatched/malformed Atom responses,
and pacing through injected clock/sleep functions. Tests require no API key,
model download, network, or real sleeping. Live collection has not been tested
against arXiv as part of this validation.

## Retrieval handoff and next stages

The versioned `paper_id` follows the `id` convention in Matias's
`Retrieval_Indexing` branch. That branch already downloads recent papers and
indexes titles and abstracts; it remains separate from this fixed-manifest
implementation. No CSV adapter or combined retrieval workflow is included.

The next PR will extract PDF text page by page. A third PR will create chunks
with source citation metadata. Later integration should agree on the corpus
and bridge this manifest to Matias's CSV rather than maintaining two competing
paper collections. This stage does not collect abstracts or categories for his
index; those fields would need to come from his metadata or a future adapter.

## Limitations

There is no retry framework, scheduled collection, latest-paper search, PDF
parsing, chunking, embeddings, generation, UI, or retrieval evaluation here.
Existing non-empty PDF files are treated as available without integrity checks.
These results establish ingestion behavior, not completed EDA or research
answer quality.
