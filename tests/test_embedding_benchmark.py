import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from indexing_pipeline.embedding_benchmark import (
    LOCAL_MODELS,
    load_questions,
    load_existing_results,
    ranked_unique_papers,
    write_results,
)
from indexing_pipeline.indexing import PaperIndexer


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class EmbeddingBenchmarkTests(unittest.TestCase):
    def test_default_question_sets_load_answerable_labels_only(self):
        question_files = [
            REPOSITORY_ROOT / "evaluation" / "benchmark_questions_2.json",
            REPOSITORY_ROOT / "evaluation" / "prompts_labeled.json",
        ]

        questions, skipped = load_questions(question_files)

        self.assertEqual(len(questions), 24)
        self.assertEqual(skipped, 3)
        self.assertEqual(
            {question["question_set"] for question in questions},
            {"benchmark_questions_2", "prompts_labeled"},
        )
        self.assertTrue(all(question["relevant_papers"] for question in questions))

    def test_local_models_include_two_new_models_and_no_paid_provider(self):
        models = {model.short_name: model for model in LOCAL_MODELS}

        self.assertIn("e5-base", models)
        self.assertIn("gte-base", models)
        self.assertTrue(all(model.provider != "openai" for model in LOCAL_MODELS))

    def test_ranked_unique_papers_keeps_first_retrieval_order(self):
        results = [
            {"paper_id": "paper-a"},
            {"paper_id": "paper-a"},
            {"paper_id": "paper-b"},
            {"paper_id": "paper-a"},
            {"paper_id": "paper-c"},
        ]

        self.assertEqual(ranked_unique_papers(results), ["paper-a", "paper-b", "paper-c"])

    def test_completed_results_can_be_resumed(self):
        question_files = [
            REPOSITORY_ROOT / "evaluation" / "benchmark_questions_2.json",
            REPOSITORY_ROOT / "evaluation" / "prompts_labeled.json",
        ]
        questions, _ = load_questions(question_files)
        question = questions[0]
        model = LOCAL_MODELS[0]
        row = {
            "model": model.short_name,
            "model_name": model.model_name,
            "question_set": question["question_set"],
            "question_id": question["id"],
            "recall_at_5": 1.0,
            "reciprocal_rank": 1.0,
            "latency_ms": 10.0,
            "retrieved_papers": "|".join(question["relevant_papers"]),
            "relevant_papers": "|".join(sorted(question["relevant_papers"])),
            "papers_added": 55,
            "chunks_added": 4529,
            "build_seconds": 1.5,
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "results.csv"
            write_results([row], output)

            resumed = load_existing_results(output, questions, (model,))

        self.assertEqual(len(resumed), 1)
        self.assertEqual(resumed[0]["question_id"], question["id"])
        self.assertEqual(resumed[0]["latency_ms"], 10.0)

    def test_batch_search_validates_indexes_once_for_all_questions(self):
        indexer = object.__new__(PaperIndexer)
        indexer.config = SimpleNamespace(embedding_provider="sentence-transformers")
        indexer.papers = object()
        indexer.chunks = object()
        dataset = SimpleNamespace(
            directory=SimpleNamespace(name="generation"),
            manifest={"included_paper_ids": ["paper-a"]},
            chunks=[SimpleNamespace(chunk_id="chunk-a")],
        )
        search_papers = Mock(return_value=[{"id": "paper-a"}])
        search_chunks = Mock(return_value=[{"paper_id": "paper-a"}])

        with (
            patch.object(indexer, "_source", return_value=(dataset, {})),
            patch.object(indexer, "_require_ids") as require_ids,
            patch.object(indexer, "_search_papers", search_papers),
            patch.object(indexer, "_search_chunks", search_chunks),
        ):
            results = list(indexer.iter_search_two_stage(["first", "second"]))

        self.assertEqual(len(results), 2)
        self.assertEqual(require_ids.call_count, 2)
        self.assertEqual(search_papers.call_count, 2)
        self.assertEqual(search_chunks.call_count, 2)
        self.assertTrue(all(result == [{"paper_id": "paper-a"}] for result, _ in results))

    def test_all_labeled_paper_ids_exist_in_manifest(self):
        questions, _ = load_questions(
            [
                REPOSITORY_ROOT / "evaluation" / "benchmark_questions_2.json",
                REPOSITORY_ROOT / "evaluation" / "prompts_labeled.json",
            ]
        )
        manifest = json.loads((REPOSITORY_ROOT / "data" / "manifest" / "papers.json").read_text(
            encoding="utf-8"
        ))
        paper_ids = {paper["paper_id"] for paper in manifest}

        self.assertTrue(
            all(
                relevant_id in paper_ids
                for question in questions
                for relevant_id in question["relevant_papers"]
            )
        )


if __name__ == "__main__":
    unittest.main()
