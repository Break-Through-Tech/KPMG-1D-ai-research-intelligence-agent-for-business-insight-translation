"""Offline behavior checks for the optional passage diversity experiment."""

import unittest

from retrieval_experiments import compare_retrieval, diversify_by_paper


def passage(chunk_id, paper_id, score):
    return {
        "chunk_id": chunk_id,
        "paper_id": paper_id,
        "page_number": 3,
        "start_character": 12,
        "end_character": 21,
        "pdf_url": f"https://example.org/{paper_id}.pdf",
        "page_text_sha256": "a" * 64,
        "text": f"Exact text for {chunk_id}",
        "score": score,
    }


class DiversityTests(unittest.TestCase):
    def test_selects_new_papers_then_fills_from_original_order_without_mutation(self):
        # Catches duplicate source rows, rewritten citations/text, or filling before diversity.
        candidates = [passage("a1", "A", 0.9), passage("a2", "A", 0.8),
                      passage("b1", "B", 0.7), passage("a3", "A", 0.6),
                      passage("c1", "C", 0.5), passage("b1", "B", 0.7)]
        before = [dict(row) for row in candidates]

        selected = diversify_by_paper(candidates, k=4)

        self.assertEqual([row["chunk_id"] for row in selected], ["a1", "b1", "c1", "a2"])
        self.assertEqual(selected, [before[i] for i in [0, 2, 4, 1]])
        self.assertEqual(candidates, before)
        self.assertIsNot(selected[0], candidates[0])

    def test_one_paper_keeps_rank_and_never_duplicates_chunks(self):
        # Catches accidental reordering when no diversity is possible.
        candidates = [passage("a1", "A", 0.9), passage("a1", "A", 0.9),
                      passage("a2", "A", 0.8)]
        self.assertEqual([row["chunk_id"] for row in diversify_by_paper(candidates, k=5)],
                         ["a1", "a2"])
        self.assertEqual(diversify_by_paper(candidates, k=0), [])


class ComparisonTests(unittest.TestCase):
    def test_compares_separate_baseline_and_larger_candidate_pool_with_latency_and_misses(self):
        # Catches comparison against the expanded pool in place of the actual k=3 baseline.
        class FakeIndexer:
            def __init__(self):
                self.calls = []

            def search_two_stage(self, question, n_papers, k):
                self.calls.append((question, n_papers, k))
                if k == 3:
                    return [passage("a1", "A", 0.9), passage("a2", "A", 0.8),
                            passage("b1", "B", 0.7)]
                return [passage("a1", "A", 0.9), passage("a2", "A", 0.8),
                        passage("a3", "A", 0.75), passage("b1", "B", 0.7),
                        passage("c1", "C", 0.6), passage("d1", "D", 0.5)]

        ticks = iter([10.0, 10.02, 20.0, 20.05])
        indexer = FakeIndexer()
        result = compare_retrieval(indexer, "question", n_papers=4, k=3,
                                   candidate_k=6, clock=lambda: next(ticks))

        self.assertEqual(indexer.calls, [("question", 4, 3), ("question", 4, 6)])
        self.assertEqual([row["chunk_id"] for row in result["baseline"]], ["a1", "a2", "b1"])
        self.assertEqual([row["chunk_id"] for row in result["variant"]], ["a1", "b1", "c1"])
        self.assertEqual(result["misses"]["baseline_only_chunk_ids"], ["a2"])
        self.assertEqual(result["misses"]["variant_only_chunk_ids"], ["c1"])
        self.assertEqual(result["misses"]["baseline_missing_from_candidates"], [])
        self.assertAlmostEqual(result["latency_ms"]["baseline"], 20.0)
        self.assertAlmostEqual(result["latency_ms"]["variant"], 50.0)
        self.assertEqual(result["variant"][1]["text"], "Exact text for b1")

    def test_rejects_candidate_pool_smaller_than_output(self):
        # Catches misleading comparisons that cannot show any extra candidate.
        with self.assertRaisesRegex(ValueError, "candidate_k"):
            compare_retrieval(None, "question", k=5, candidate_k=4)


if __name__ == "__main__":
    unittest.main()
