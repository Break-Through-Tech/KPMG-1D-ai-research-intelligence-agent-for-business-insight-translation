"""End-to-end checks against a real local passage index and an isolated answer client."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from answer_pipeline import main, run_workflow
from indexing_pipeline.config import IndexingConfig
from indexing_pipeline.indexing import PaperIndexer
from research_pipeline.config import PipelineConfig
from research_pipeline.pipeline import run_chunking
from research_pipeline.storage import write_jsonl
from tests.pr3_fixtures import page, paper
from tests.test_indexing_pipeline import DeterministicEmbedding


PAPER_ID = "2608.20316v1"


class RecordingClient:
    def __init__(self, response, stop_reason="end_turn"):
        self.response = response
        self.stop_reason = stop_reason
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(stop_reason=self.stop_reason,
                               content=[SimpleNamespace(type="text", text=self.response)])


class AnswerPipelineTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        metadata = {**paper().to_dict(), "abstract": "Caching reduces agent costs.",
                    "url": f"https://arxiv.org/abs/{PAPER_ID}"}
        (root / "manifest.json").write_text(json.dumps([metadata]), encoding="utf-8")
        write_jsonl(root / "pages.jsonl", [page("Caching repeated tool responses reduces agent compute cost.").to_dict()])
        run_chunking(PipelineConfig(repository_root=root, manifest_path=Path("manifest.json"),
                                    extracted_pages_path=Path("pages.jsonl")))
        self.indexer = PaperIndexer(IndexingConfig(repository_root=root, manifest_path=Path("manifest.json"),
                                                   chroma_directory=Path("chroma")),
                                    embedding_function=DeterministicEmbedding())
        self.indexer.index_papers()
        self.indexer.index_chunks()

    def test_article_question_retrieves_real_passage_and_summarizes_with_citation(self):
        client = RecordingClient(f"Caching can reduce repeated work [{PAPER_ID} p.1].")

        result = run_workflow(self.indexer, "How can agents cut compute cost?", paper_id=PAPER_ID, client=client)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["summary"], f"Caching can reduce repeated work [{PAPER_ID} p.1].")
        self.assertEqual(result["citations"], [f"{PAPER_ID} p.1"])
        self.assertEqual(len(result["passages"]), 1)
        self.assertEqual(result["passages"][0]["text"], "Caching repeated tool responses reduces agent compute cost.")
        self.assertEqual(result["passages"][0]["paper_id"], PAPER_ID)
        self.assertIn("Caching repeated tool responses", client.calls[0]["messages"][0]["content"])
        self.assertIn("How can agents cut compute cost?", client.calls[0]["messages"][0]["content"])

    def test_unknown_article_is_rejected_before_answer_call(self):
        client = RecordingClient("irrelevant")

        with self.assertRaisesRegex(ValueError, "not in the active index"):
            run_workflow(self.indexer, "How can agents cut compute cost?",
                         paper_id="9999.99999v1", client=client)
        self.assertEqual(client.calls, [])

    def test_unretrieved_citation_is_flagged_for_review(self):
        client = RecordingClient("An unsupported claim [9999.99999v1 p.9].")

        result = run_workflow(self.indexer, "How can agents cut compute cost?", client=client)

        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["unsupported_citations"], ["9999.99999v1 p.9"])
        self.assertEqual(len(result["passages"]), 1)

    def test_truncated_summary_is_flagged_for_review(self):
        client = RecordingClient(f"Caching helps [{PAPER_ID} p.1].", stop_reason="max_tokens")

        result = run_workflow(self.indexer, "How can agents cut compute cost?", client=client)

        self.assertEqual(result["status"], "needs_review")

    def test_malformed_extra_citation_cannot_hide_behind_valid_citation(self):
        client = RecordingClient(f"Caching helps [{PAPER_ID} p.1]. Another claim [9999.99999 p.9].")

        result = run_workflow(self.indexer, "How can agents cut compute cost?", client=client)

        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["unsupported_citations"], ["9999.99999 p.9"])

    def test_empty_question_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "question"):
            run_workflow(self.indexer, "  ", client=RecordingClient("unused"))

    def test_cli_emits_reviewable_json_for_one_question(self):
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["--question", "How can agents cut compute cost?", "--paper-id", PAPER_ID],
                             indexer=self.indexer,
                             client=RecordingClient(f"Caching helps [{PAPER_ID} p.1]."))

        self.assertEqual(exit_code, 0)
        record = json.loads(output.getvalue())
        self.assertEqual(record["status"], "ok")
        self.assertEqual(record["paper_id"], PAPER_ID)
        self.assertEqual(record["passages"][0]["pdf_url"], f"https://arxiv.org/pdf/{PAPER_ID}")

    def test_retrieval_only_cli_returns_evidence_without_answer_client(self):
        client = RecordingClient("should not be used")
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["--question", "How can agents cut compute cost?", "--retrieval-only"],
                             indexer=self.indexer, client=client)

        self.assertEqual(exit_code, 0)
        record = json.loads(output.getvalue())
        self.assertEqual(record["status"], "retrieval_only")
        self.assertIsNone(record["summary"])
        self.assertEqual(len(record["passages"]), 1)
        self.assertEqual(client.calls, [])

    def test_cli_reports_missing_answer_credentials_without_traceback(self):
        errors = io.StringIO()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}), redirect_stderr(errors):
            exit_code = main(["--question", "How can agents cut compute cost?"], indexer=self.indexer)

        self.assertEqual(exit_code, 3)
        self.assertIn("ANTHROPIC_API_KEY", json.loads(errors.getvalue())["error"])


if __name__ == "__main__":
    unittest.main()
