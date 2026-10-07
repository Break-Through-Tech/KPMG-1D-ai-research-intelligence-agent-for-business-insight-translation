# PR3 local engineering verification

Implementation base: merged PR2 main `2712b797a31b219060abf83e8a7637475b39c606`.
The verification described below was completed before any commit or push.
Shah subsequently approved committing and pushing the reviewed branch only;
PR creation and merging are not part of that approval.
Work lives in the existing isolated Team 1D
checkout; the original dirty prototype checkout is preserved.

## Executed evidence

- All 106 offline unittest cases passed, including the original 55 tests.
- Representative five-paper runs succeeded for all three profiles with socket
  connections blocked. All 104 pages were independently re-extracted and matched
  stored cleaned text; every chunk reconstructed exactly from source offsets and
  every character of each nonblank page was covered.
- Each profile ran twice. All five generation artifacts and the active pointer
  were byte-identical; source PDF hashes were unchanged.

| Profile | Chunks | Repeated generation/manifest SHA-256 |
|---|---:|---|
| Boundary-aware characters, 1800/200 | 286 | `3e914a6077e4c4f2a3482f0613338abb35ea1b15a713a66ea863bf09279b6cfb` |
| Fixed characters, 1800/200 | 271 | `5a32c80d30e21a10a3cce8ff9badbfabb37d4ff5665357bffefcb21301037a90` |
| Local synthetic WordPiece, 200/40/256 | 2493 | `f05b050ef1da0e004fcee7ee7b295aab4d212e0f32ff0a50c1d73210ee69b782` |

The synthetic tokenizer uses the actual tokenizers implementation but an
intentionally tiny vocabulary. Its count is **not** a MiniLM result, a quality
comparison or a recommended corpus size. Token counts were independently
recomputed for every emitted token-profile chunk, including special tokens.

Source page output remains exactly PR2's 373,976 cleaned characters and SHA-256
`afb19df94fc17cd4e369bf0a07e4e6f9be0c2682043c708f1f80e5bc0e5a7e1a`.
The paper catalog also matches PR1/PR2's stored hash. There are no blank pages
in the five supplied PDFs; blank-page behavior is covered with real-PDF tests.

Failure checks seed prior data and inject staging, directory rename and pointer
replacement failures, source mutation, partial/empty corpora and interruption
before pointer selection. Previous selected data remains unchanged. Loader
checks exercise corruption with recomputed hashes as well as byte tampering,
bad citation metadata, offsets, schemas, manifests and symlinks.

The 36 core metadata/ingestion/path/storage/download tests pass under Python's
`-S` flag without site packages. Legacy ingestion and extraction commands still
succeed and retain their original catalog/page hashes. Standalone chunking and
inspection succeed on those pages without reparsing PDFs. Compilation,
`pip check`, tracked/untracked whitespace checks and a scan for private-key/API
token patterns or machine-specific paths in deliverable files passed.

## Commands

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
PYTHONPATH=src .venv/bin/python -m tests.validate_pr3_corpus
PYTHONPATH=src .venv/bin/python -m research_pipeline.cli run
PYTHONPATH=src .venv/bin/python -m research_pipeline.cli inspect
PYTHONPATH=src .venv/bin/python -S -m unittest tests.test_ingestion tests.test_metadata tests.test_manifest_paths tests.test_collection_hardening tests.test_storage -q
.venv/bin/python -m compileall -q src tests
.venv/bin/python -m pip check
git diff --check
```

The corpus verifier needs the optional tokenizer requirements, creates a local
synthetic asset and removes its temporary generations after comparison. Normal
character-profile operation needs no tokenizer package or asset.

## Compatibility versus integration

The real metadata CSV in the locally fetched Team 1D `origin/Retrieval_Indexing`
reference has ten canonical versioned IDs; our five-paper corpus has no shared
IDs. The read-only coverage command reports 0 shared, 5 passage-only and 10
metadata-only IDs. Canonical `paper_id`/CSV `id` compatibility and passage
filtering are tested, but a working two-stage retrieval integration is **not**
established. Matias and the team need to agree on one overlapping corpus before
connecting his abstract-level candidates to these passages.

## Remaining unverified / intentionally excluded

- Actual MiniLM or other embedding-model tokenizer assets and semantic retrieval
  quality; no weights, embeddings or model benchmark ran.
- CSV conversion, passage indexing, combined retrieval and generation.
- Cross-platform/cross-version bitwise reproducibility beyond the recorded
  local environment, hostile concurrent writers and power-loss durability.
- Original PDF layout fidelity, OCR, tables/equations/figures or semantic paper
  authenticity. Exact cleaned-text reconstruction does not prove source parsing
  or an eventual generated claim is correct.

The future evaluation document specifies Recall@5, MRR, citation support and
latency without executing retrieval evaluation or including labels in the corpus.

## Independent review and corrections

A fresh read-only reviewer independently ran the then-current 100-test suite.
No critical findings. Three important findings were reproduced with failing
tests, fixed and verified with the final 106-test suite:

1. Protect the local tokenizer asset against same-path, hardlink/symlink and
   containing-run-root output aliases. Detect asset mutation before/after work.
2. Preserve stable missing-PDF, parse-failure, no-text and missing-page categories
   without storing machine-specific exception paths. A mixed usable/missing/
   corrupt/zero-page corpus verifies the diagnoses; zero-byte PDFs can still be
   explicitly published as partial data.
3. Validate every quality-report coverage/count/blank-page/tokenizer-status field
   against actual records. Reject rehashed contradictions and incomplete failure
   classifications/source hashes.

The dependency-provenance finding was regraded as important because rejecting
incomplete provenance is an explicit requirement. The loader now requires Python
for all modes and pypdf/fonttools for PDF mode. Its regression failed before the
fix and passed after it.

Deferred minor: a deterministic fingerprint of uncommitted implementation source.
Current artifacts record algorithm/configuration/input/dependency provenance and
the base revision is recorded here, but reproducing this uncommitted work still
requires preserving these source files. A source fingerprint could distinguish
future edits that fail to bump the algorithm version; it was not added as a new
versioning subsystem.

## Execution rulings and accepted limits

- Reuse the clean isolated Team 1D clone rather than a native managed worktree
  that would target this chat's Team 1F repository. Cost: review and later
  integration must use this separate checkout, not the old dirty prototype.
- Review files directly, including untracked files, instead of an empty committed
  range. Cost: a later commit/PR diff still needs its normal review.
- Keep the branch and plan ledger without cleanup because commits are forbidden.
  Cost: this uncommitted checkout must be retained until an approved handoff.
- Actual MiniLM/BGE assets and behavior remain unverified; cost: do not use these
  results to claim model compatibility or select a winning embedding model.
- Retrieval/indexing/evaluation/generation remain outside PR3; cost: Task #1 and
  end-user answer quality still require follow-up experiments.
- Matias's corpus has zero overlap; cost: agree on shared IDs before attempting
  a candidate-to-passage retrieval integration.
- Power loss, adversarial races and concurrent writers are excluded; cost: this
  is a local single-writer preparation protocol, not production durability.
- OCR, PDF layout and semantic authenticity are excluded; cost: users must verify
  important evidence in original PDFs, not treat reconstructed text as proof.
- Cross-platform/dependency-version bitwise consistency is unverified; cost:
  rerun the verifier in any new environment before relying on identical hashes.
- Large-corpus performance is unmeasured; cost: profile memory/runtime before
  materially expanding beyond the five-paper fixture.
- Historical originality was not audited by the reviewer. Development here used
  Team 1D's contracts and independently written code, with no Team 1F source read
  or copied during implementation; cost: the review is not a provenance audit.

PR3 passed local review-readiness verification. Shah subsequently approved
committing and pushing the branch, but not PR creation or merging. This does not
declare retrieval integration complete.
