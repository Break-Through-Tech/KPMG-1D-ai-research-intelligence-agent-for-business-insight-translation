# Initial retrieval and summarization workflow evaluation

## What was exercised

On 2026-11-04, the workflow used the existing 25-paper active generation
`c8f1286a93a4c0fac99c92a8eb5e0e6a99fab973fc7f988717bf0326876b025d`,
its synchronized Chroma index, the configured `all-MiniLM-L6-v2` embedding
model, 10 first-stage paper candidates, and five passages per question. The
four development questions BQ-01 through BQ-04 came from
`evaluation/benchmark_questions.json`. The candidate questions BQ-05 through
BQ-08 were left untouched pending the human-reviewed evaluation split.

The new command ran each question through paper ranking and passage vector
search. The results below are observed retrieval outputs, not model-generated
summaries or relevance scores. Scores are rounded cosine similarities, not
calibrated confidence.

| Question | Top retrieved passage | Score | Initial inspection |
|---|---|---:|---|
| BQ-01, model routing | `2608.20316v1` p.27 | 0.610 | Retrieved passages discuss costly value estimation and routing; one top-five passage is in references. |
| BQ-02, financial research quality | `2609.35744v1` p.2 | 0.515 | Retrieved passages cover financial evaluation rubrics and source rechecking; one top-five passage is in references. |
| BQ-03, agent failure reporting | `2609.35732v1` p.1 | 0.647 | Three passages come from page 1 of the failure-reporting paper, with overlapping evidence. |
| BQ-04, token forecasting | `2609.35760v1` p.2 | 0.616 | Retrieved passages cover forecasting and budget-control replay; one top-five passage is in references. |

The offline end-to-end test publishes a sample research article, indexes its
passage with a deterministic test embedding, asks a business question, and
passes the retrieved passage to an injected answer client. It checks that the
returned summary cites the actual paper/page and retains the source passage.
Other tests verify article selection, invalid article rejection, unsupported
citation flagging, retrieval-only operation, and the missing-credential error.
The injected client's fixed text checks integration, not generated answer
quality.

## Reproduce

From the repository root, with the active generation and Chroma index already
built as described in the README:

```bash
PYTHONPATH=src python -m answer_pipeline --retrieval-only \
  --question 'When is it worth paying for a more accurate model-routing estimate instead of using a cheaper signal?' \
  --question 'What should a financial services team check before trusting a research report produced by an AI agent?' \
  --question 'How should a tool-using AI agent report a failed task so that a human reviewer can understand what went wrong?' \
  --question 'How could forecasting token use help an enterprise budget for long-running AI agent workflows?'
PYTHONPATH=src python -m unittest tests.test_answer_pipeline -v
```

For generated summaries, omit `--retrieval-only` and set
`ANTHROPIC_API_KEY`. The command returns `ok` when at least one citation names
a retrieved paper/page and no citation names an unreturned paper/page. It
returns `needs_review` for missing or unreturned citations. This check cannot
establish that a cited passage actually supports a claim.

## Limits and next evaluation step

No Anthropic API key was available for this run, so no live generated summary
or answer-quality score is reported. No human-reviewed relevance labels are
available, so Recall@5, MRR, and claim-support rates cannot be calculated.
The reference-section and duplicate-page hits are concrete review targets.
Human reviewers should mark supporting source spans, freeze a held-out split,
then score retrieval and summaries using the protocol in
`docs/chunking_evaluation_plan.md`.
