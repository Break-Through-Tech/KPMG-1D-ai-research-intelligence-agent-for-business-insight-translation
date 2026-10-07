# Future comparison of chunking profiles (not implemented in PR3)

Task #1 should compare `fixed_characters`, `boundary_characters` and `tokenizer`
using the same agreed paper corpus, embedding model/revision, tokenizer, distance
metric, vector-index parameters and query formatting. Only chunk boundaries
change. Character profiles may exceed a model's token limit: measure this and
report truncation/invalid inputs rather than silently crediting lost evidence.
Use an explicit model-specific budget/template for the tokenizer profile.
MiniLM is a baseline, not an established winner; research on other models is a
hypothesis to test, not a result from this data-preparation work.

1. Agree on paper IDs with Matias and create separate reproducible passage
   collections for each profile. Do not overwrite his abstract-level collection.
2. Create representative business-oriented questions with human-reviewed relevant
   paper/page/source spans. Keep questions, expected answers and labels outside
   the indexed corpus. Use development questions for tuning and reserve untouched
   evaluation questions; do not tune overlap using held-out results.
3. Map retrieved chunks to those source spans, not profile-dependent chunk IDs.
   Define a relevant hit before evaluating (for example, contains a sufficient
   adjudicated supporting span). Deduplicate overlapping chunks covering the same
   evidence item so overlap cannot artificially improve the evidence count.
4. Report the following metrics with explicit denominators and per-question
   results, not just averages:

| Metric | Definition |
|---|---|
| Recall@5 | Number of distinct labeled evidence items represented in the top five retrieved chunks divided by all labeled evidence items for that question. Questions with no labeled relevant evidence are reported separately, not divided by zero. |
| MRR | Mean of reciprocal rank of the first relevant result in the agreed top-k list, assigning zero when no relevant result is found. Declare k and tie-breaking rules. |
| Citation correctness | Separately report exact span/metadata reconstruction and human judgment that the cited passage actually supports the claim. Reconstruction alone does not establish factual support. |
| Retrieval latency | Warm and cold p50/p95 query latency including query embedding and vector search. Measure reranking separately if later added; exclude dataset build/index time and report those costs independently. Record hardware, repeated trials and caching conditions. |

Start with direct passage retrieval. A later experiment may compare Matias's
abstract-level candidate selection followed by paper-filtered passage search.
Candidate-stage misses need separate recall measurement; zero corpus overlap
cannot demonstrate a working two-stage system. Keep model choice, reranking and
corpus expansion separate from the first chunk-boundary comparison.

Five papers support debugging and an initial demo, not statistically convincing
quality claims. Expand corpus and query diversity, review answerability and
report uncertainty before choosing a final approach. PR3 runs no retrieval,
model benchmark, generation or evaluation, and no evaluation labels enter its
published datasets.
