# Optional passage diversity experiment

This experiment sits after `PaperIndexer.search_two_stage()` and does not
change the index, default retriever, embedding model, or published passage data.
It is an ordering experiment, **not** a relevance or answer-quality result.

## Variant and contract

`diversify_by_paper(passages, k)` reads an ordered candidate list. It keeps the
first (highest-ranked) passage from each distinct `paper_id`, then fills any
remaining slots from the original order. The first hit remains first. Duplicate
`chunk_id` rows are returned only once. Selection is deterministic for a given
ordered candidate list; ties inherit the indexer's input order.

The variant uses neither numeric scores nor text similarity. Chroma's `score`
is retained exactly as returned; it is **not calibrated confidence**. Each
selected dictionary is copied without editing `chunk_id`, `paper_id`,
`page_number`, `start_character`, `end_character`, `pdf_url`,
`page_text_sha256`, `text`, or any additional source field. It never rewrites
source text. The policy can promote weak passages from other papers and remove
strong supporting passages from the best paper; that tradeoff needs review.

`compare_retrieval()` runs the current baseline with `k=5`, then calls the
unchanged retriever again with `candidate_k=20` and applies the variant. Its
`latency_ms.variant` includes the expanded two-stage search and the local
selection. Its `misses.baseline_only_chunk_ids` and
`misses.variant_only_chunk_ids` are set differences between top-five results;
`baseline_missing_from_candidates` detects baseline IDs missing from the
larger search response. These are **not relevance misses**. Without reviewed
labels, neither list says which result is better.

## Reproduce

From the repository root, after publishing the active passage generation and
building the MiniLM index as described in the README:

```bash
PYTHONPATH=src .venv/bin/python -m retrieval_experiments \
  --question 'When is it worth paying for a more accurate model-routing estimate instead of using a cheaper signal?' \
  --question 'What should a financial services team check before trusting a research report produced by an AI agent?' \
  --question 'How should a tool-using AI agent report a failed task so that a human reviewer can understand what went wrong?' \
  --question 'How could forecasting token use help an enterprise budget for long-running AI agent workflows?'
```

The command prints one compact JSON record per question. The Python API returns
the complete original passage dictionaries for citation inspection. The CLI
uses the configured `PaperIndexer` and requires its matching embedding model
and synchronized active index; it does not build or mutate that index.

For the offline checks:

```bash
PYTHONPATH=src .venv/bin/python -m unittest tests.test_retrieval_experiments -v
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
```

## Development-only observation, 2026-10-28

Only BQ-01 through BQ-04 from `evaluation/benchmark_questions.json` were run
here. BQ-05 through BQ-08 were not run or tuned on in this experiment;
they should stay outside development work until the evaluation owner defines
the reviewed labels and split. The settings were 10 candidate papers, baseline
top 5, expanded passage pool top 20, and the existing `all-MiniLM-L6-v2`
index over the 25-paper active corpus. After one warm-up search, three repeats
per question produced the following median wall-clock times on this local Mac.
All three repeats returned the same ordered chunk IDs for both methods.

| Question | Baseline paper IDs in rank order | Variant paper IDs in rank order | Baseline-only / variant-only passages | Baseline missing from larger pool | Median baseline / variant latency |
|---|---|---|---:|---:|---:|
| BQ-01 | `2608.20316v1` × 5 | `2608.20316v1`, `2608.20320v1`, `2609.35751v1`, `2608.20316v1` × 2 | 2 / 2 | 0 | 419.4 / 480.3 ms |
| BQ-02 | `2609.35744v1` × 3, `2609.35732v1`, `2609.35744v1` | `2609.35744v1`, `2609.35732v1`, `2610.18868v1`, `2610.18861v1`, `2608.20318v1` | 3 / 3 | 0 | 466.7 / 462.0 ms |
| BQ-03 | `2609.35732v1` × 3, `2610.18861v1` × 2 | `2609.35732v1`, `2610.18861v1`, `2608.20319v1`, `2610.18842v1`, `2609.35741v1` | 3 / 3 | 0 | 419.0 / 424.4 ms |
| BQ-04 | `2609.35760v1` × 5 | `2609.35760v1`, `2608.20316v1`, `2608.20318v1`, `2610.18874v1`, `2609.35760v1` | 3 / 3 | 0 | 430.3 / 425.2 ms |

The wall-clock measurements include local embedding/query overhead and are
exploratory, not a benchmark. The first attempt to run the CLI needed the
public MiniLM model downloaded into temporary cache; the measurements above
used that cached model with network disabled. The index and corpus were not
modified. The apparently similar timings do not establish a latency or quality
gain, especially with three repeats on one machine.

**Next evaluation gate:** Person 1's reviewed passage labels should score both
rankings on a fixed split, report actual relevant-passage misses and citation
support, and decide whether any paper-diversity benefit outweighs lost
same-paper evidence. No threshold or weight was tuned on these questions.
