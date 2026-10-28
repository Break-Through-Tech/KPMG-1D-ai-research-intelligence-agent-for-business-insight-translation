# Validated passage indexing design

## Intent
Connect the existing paper search prototype to the published, citation-preserving passage dataset. This gives retrieval one verified corpus and makes source offsets available for answer review. Work stays on `codex/validated-passage-indexing`; no merge to main.

## Goals
- Fail closed when the active dataset is missing or fails validation.
- Index only papers and chunks included in that active generation.
- Use published chunk IDs, text, paper IDs, physical PDF pages, and source offsets.
- Make repeated indexing idempotent and remove stale vectors after a generation changes.
- Keep the current two-stage query API and use offline tests with a local vector database.
- Prepare a small, separate question set for human evidence labeling; do not claim retrieval quality without those labels.

## Non-goals
No live arXiv collection, hosted model call, embedding model comparison, or automatic answer grading in this change. The existing Claude answer prototype remains a draft.

## Approaches
1. Continue slicing committed `pages.jsonl` in the indexer. Simple, but bypasses validation and produces a second chunk scheme.
2. Index the active pipeline generation directly. This keeps the existing paper search and uses the validated chunks, IDs, and source offsets. Chosen approach.
3. Replace two-stage search with passage-only search. A useful future evaluation baseline, but it would remove the team's current paper candidate stage.

## Contract
`PaperIndexer` loads the active generation through `load_active_dataset` before indexing. The paper manifest must match the dataset's validated metadata; abstracts and URLs remain search-only metadata. Indexing includes only `included_paper_ids`. Chroma records carry the generation identity and citation location. Reindexing reconciles collection records to the selected generation. A failed validation or metadata mismatch must leave the existing index untouched. Tests inject a deterministic embedding function and use a temporary persistent Chroma database.

## Evaluation handoff
Store candidate business questions outside the indexed corpus with no expected answer in the source index. Human reviewers will mark supporting paper/page/source spans before Recall@5, MRR, and citation support are reported, following `docs/chunking_evaluation_plan.md`.
