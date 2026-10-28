"""Offline checks that search indexes one validated, selected passage generation."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from initializer import initialize
from indexing_pipeline.config import IndexingConfig
from retrieval_pipeline.config import RetrievalConfig
from indexing_pipeline.indexing import PaperIndexer
from research_pipeline.chunking import ChunkingConfig
from research_pipeline.config import PipelineConfig
from research_pipeline.datasets import load_active_dataset
from research_pipeline.pipeline import run_chunking
from research_pipeline.storage import write_jsonl
from tests.pr3_fixtures import page, paper


class DeterministicEmbedding:
    """Small local embedding; no model weights or network calls."""

    def __call__(self, input):
        return [[float(len(text)), float(text.count("a") + 1), 1.0] for text in input]

    def embed_query(self, input):
        return self(input)

    def name(self):
        return "deterministic-test"


class IndexingPipelineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.manifest_path = self.root / "manifest.json"
        self.pages_path = self.root / "pages.jsonl"
        self.record = {**paper().to_dict(), "abstract": "Research abstract", "url": "https://arxiv.org/abs/2608.20316v1"}
        self.manifest_path.write_text(json.dumps([self.record]), encoding="utf-8")
        self.pipeline_config = PipelineConfig(repository_root=self.root, manifest_path=Path("manifest.json"),
                                              extracted_pages_path=Path("pages.jsonl"))
        self.config = IndexingConfig(repository_root=self.root, manifest_path=Path("manifest.json"),
                                     chroma_directory=Path("chroma"))
        self.publish("abcdefghij")
        self.indexer = PaperIndexer(self.config, embedding_function=DeterministicEmbedding())

    def publish(self, text):
        write_jsonl(self.pages_path, [page(text).to_dict()])
        result = run_chunking(self.pipeline_config, ChunkingConfig(profile="fixed_characters", size=6, overlap=2))
        self.assertTrue(result["artifacts_published"])
        return load_active_dataset(self.root / "data/processed/runs", self.root / "data/processed/active_run.json")

    def test_index_uses_verified_chunk_ids_text_offsets_and_generation(self):
        dataset = load_active_dataset(self.root / "data/processed/runs", self.root / "data/processed/active_run.json")
        self.assertEqual(self.indexer.index_papers(), 1)
        self.assertEqual(self.indexer.index_chunks(), 2)
        stored = self.indexer.chunks.get(include=["documents", "metadatas"])
        self.assertEqual(set(stored["ids"]), {chunk.chunk_id for chunk in dataset.chunks})
        for chunk_id, document, metadata in zip(stored["ids"], stored["documents"], stored["metadatas"]):
            source = next(chunk for chunk in dataset.chunks if chunk.chunk_id == chunk_id)
            self.assertEqual(document, source.text)
            self.assertEqual(metadata["paper_id"], source.paper_id)
            self.assertEqual(metadata["page_number"], source.page_number)
            self.assertEqual(metadata["start_character"], source.start_character)
            self.assertEqual(metadata["end_character"], source.end_character)
            self.assertEqual(metadata["generation"], dataset.directory.name)
        self.assertEqual(self.indexer.index_papers(), 0)
        self.assertEqual(self.indexer.index_chunks(), 0)
        passages = self.indexer.search_two_stage("abc", n_papers=1, k=1)
        self.assertEqual(len(passages), 1)
        self.assertIn(passages[0]["chunk_id"], stored["ids"])
        self.assertIn("start_character", passages[0])
        self.assertIn("end_character", passages[0])

    def test_changed_active_generation_removes_old_vectors(self):
        self.indexer.index_papers()
        self.indexer.index_chunks()
        before = set(self.indexer.chunks.get()["ids"])
        dataset = self.publish("different page content")
        self.indexer.index_papers()
        self.indexer.index_chunks()
        after = set(self.indexer.chunks.get()["ids"])
        self.assertEqual(after, {chunk.chunk_id for chunk in dataset.chunks})
        self.assertFalse(before & after)
        self.assertEqual({m["generation"] for m in self.indexer.chunks.get(include=["metadatas"])["metadatas"]},
                         {dataset.directory.name})

    def test_initialize_publishes_passages_before_indexing(self):
        pointer = self.root / "data/processed/active_run.json"
        pointer.unlink()
        config = RetrievalConfig(repository_root=self.root, manifest_path=Path("manifest.json"),
                                 pages_path=Path("pages.jsonl"), downloaded_directory=Path("downloads"))
        with patch("initializer.PaperRetriever.download_latest", return_value=[]), redirect_stdout(io.StringIO()):
            indexer = initialize(n_papers=0, retrieval_config=config,
                                 embedding_function=DeterministicEmbedding())
        dataset = load_active_dataset(self.root / "data/processed/runs", pointer)
        self.assertEqual(set(indexer.chunks.get()["ids"]), {chunk.chunk_id for chunk in dataset.chunks})
        self.assertEqual(indexer.papers.count(), 1)

    def test_missing_active_dataset_fails_before_creating_vector_database(self):
        pointer = self.root / "data/processed/active_run.json"
        pointer.unlink()
        config = IndexingConfig(repository_root=self.root, manifest_path=Path("manifest.json"),
                                chroma_directory=Path("unused-chroma"))
        with self.assertRaises((OSError, ValueError)):
            PaperIndexer(config, embedding_function=DeterministicEmbedding())
        self.assertFalse((self.root / "unused-chroma").exists())

    def test_invalid_active_dataset_or_manifest_mismatch_does_not_mutate_index(self):
        self.indexer.index_papers()
        self.indexer.index_chunks()
        paper_ids = self.indexer.papers.get()["ids"]
        chunk_ids = self.indexer.chunks.get()["ids"]
        pointer = self.root / "data/processed/active_run.json"
        saved = pointer.read_bytes()
        pointer.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.indexer.index_chunks()
        pointer.write_bytes(saved)
        self.record["title"] = "Mismatched title"
        self.manifest_path.write_text(json.dumps([self.record]), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.indexer.index_papers()
        self.assertEqual(self.indexer.papers.get()["ids"], paper_ids)
        self.assertEqual(self.indexer.chunks.get()["ids"], chunk_ids)


if __name__ == "__main__":
    unittest.main()
