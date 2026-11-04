"""Optional, rank-only paper diversity experiment for two-stage passage search.

This module never changes PaperIndexer or its default search ordering. Returned
passage dictionaries retain the indexer's exact citation and source fields.
"""

import argparse
import json
from time import perf_counter


def diversify_by_paper(passages, k=5):
    """Take one ranked passage per paper, then fill from original rank order.

    Input order is the relevance order supplied by search_two_stage. Scores are
    neither compared nor interpreted as probabilities. Duplicate chunk IDs are
    discarded after their first appearance, and returned rows are shallow copies.
    """
    if k <= 0:
        return []

    unique = []
    seen_chunks = set()
    for passage in passages:
        chunk_id = passage["chunk_id"]
        if chunk_id not in seen_chunks:
            unique.append(passage)
            seen_chunks.add(chunk_id)

    selected = []
    selected_chunks = set()
    selected_papers = set()
    for passage in unique:
        if passage["paper_id"] not in selected_papers:
            selected.append(dict(passage))
            selected_chunks.add(passage["chunk_id"])
            selected_papers.add(passage["paper_id"])
            if len(selected) == k:
                return selected

    for passage in unique:
        if passage["chunk_id"] not in selected_chunks:
            selected.append(dict(passage))
            if len(selected) == k:
                break
    return selected


def compare_retrieval(indexer, question, *, n_papers=10, k=5, candidate_k=20,
                      clock=perf_counter):
    """Measure baseline and diversity variant separately for one question.

    Misses describe differences between result lists, not relevance misses.
    Variant latency includes the expanded two-stage search and reranking.
    """
    if k < 1 or candidate_k <= k:
        raise ValueError("candidate_k must be larger than positive k")
    if n_papers < 1:
        raise ValueError("n_papers must be positive")

    start = clock()
    baseline = indexer.search_two_stage(question, n_papers=n_papers, k=k)
    baseline_ms = (clock() - start) * 1000

    start = clock()
    candidates = indexer.search_two_stage(question, n_papers=n_papers, k=candidate_k)
    variant = diversify_by_paper(candidates, k=k)
    variant_ms = (clock() - start) * 1000

    baseline_ids = {row["chunk_id"] for row in baseline}
    variant_ids = {row["chunk_id"] for row in variant}
    candidate_ids = {row["chunk_id"] for row in candidates}
    return {
        "question": question,
        "baseline": baseline,
        "variant": variant,
        "latency_ms": {"baseline": baseline_ms, "variant": variant_ms},
        "misses": {
            "baseline_only_chunk_ids": [row["chunk_id"] for row in baseline
                                        if row["chunk_id"] not in variant_ids],
            "variant_only_chunk_ids": [row["chunk_id"] for row in variant
                                       if row["chunk_id"] not in baseline_ids],
            "baseline_missing_from_candidates": [row["chunk_id"] for row in baseline
                                                 if row["chunk_id"] not in candidate_ids],
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--question", action="append", required=True,
                        help="Development question; repeat for multiple questions")
    parser.add_argument("--n-papers", type=int, default=10)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--candidate-k", type=int, default=20)
    args = parser.parse_args(argv)

    from indexing_pipeline.indexing import PaperIndexer

    indexer = PaperIndexer()
    for question in args.question:
        result = compare_retrieval(indexer, question, n_papers=args.n_papers,
                                   k=args.k, candidate_k=args.candidate_k)
        compact = {
            "question": question,
            "baseline": [{field: passage[field] for field in ("chunk_id", "paper_id", "page_number")}
                         for passage in result["baseline"]],
            "variant": [{field: passage[field] for field in ("chunk_id", "paper_id", "page_number")}
                        for passage in result["variant"]],
            "latency_ms": result["latency_ms"],
            "misses": result["misses"],
        }
        print(json.dumps(compact, sort_keys=True))


if __name__ == "__main__":
    main()
