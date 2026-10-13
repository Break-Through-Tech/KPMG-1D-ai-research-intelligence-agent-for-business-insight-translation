# Draft PR3 description — not submitted

## Purpose

Build on PR1's validated paper identities and PR2's cleaned, page-aware text to
produce traceable passage inputs for Task #1 embedding/vector-search prototypes.
The implementation is independently developed for Team 1D and its existing
contracts. Learning from other teams' approaches is welcome; copying their code
or documentation is not the development method.

## Scope

- Three deterministic profiles: boundary-aware characters, fixed characters and
  optional actual local-tokenizer budgets.
- Exact Unicode source spans, content-sensitive IDs and unchanged citation metadata.
- Source/configuration/dependency/artifact hashes, complete coverage declarations
  and immutable generation directories selected by one atomic active pointer.
- Validating model-neutral loaders, standalone chunking and combined offline CLI.
- Read-only CSV ID coverage and optional paper filtering for Matias's handoff.
- Offline edge-case/failure tests, real-corpus verifier and future evaluation plan.

No embeddings, vector indexing, CSV conversion, combined retrieval, LLM
generation, OCR, UI or evaluation execution. Existing ingestion/extraction
commands and paths remain intact. The combined runner uses scratch copies of
their stages rather than replacing legacy outputs.

## Review

See [verification evidence and remaining limitations](pr3_validation.md),
[operational/data contracts](pipeline.md), and
[the future controlled comparison](chunking_evaluation_plan.md).
Shah approved committing and pushing the reviewed branch after verification.
This document remains a draft, not a submitted GitHub PR; merging is not authorized.
