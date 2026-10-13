"""Real offline PDFs exercise all preparation stages and failure preservation."""

from dataclasses import replace
import importlib
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from research_pipeline.chunking import ChunkingConfig
from research_pipeline.config import PipelineConfig
from research_pipeline.datasets import load_active_dataset
from research_pipeline.storage import write_json, write_jsonl
from tests.test_extraction_cli import write_fixture_pdf, SECOND_RECORD
from tests.test_ingestion import VALID_RECORD
from tests.pr3_fixtures import page


class PipelineTests(unittest.TestCase):
    def setUp(self):
        try:
            self.api = importlib.import_module("research_pipeline.pipeline")
        except ImportError:
            self.fail("PR3 combined runner is not implemented")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = PipelineConfig(repository_root=self.root)
        self.run_root = self.root / "data/processed/runs"
        self.pointer = self.root / "data/processed/active_run.json"
        self.manifest = self.config.resolve(self.config.manifest_path)
        write_json(self.manifest, [VALID_RECORD])
        write_fixture_pdf(self.root / VALID_RECORD["source_path"], ["first page", None, "last page"])
        for field in ("paper_catalog_path", "extracted_pages_path"):
            path = self.config.resolve(getattr(self.config, field))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"prior independent stage output\n")

    def run_pipeline(self, **changes):
        return self.api.run_pipeline(self.config, ChunkingConfig(), **changes)

    def test_real_end_to_end_is_offline_deterministic_and_preserves_old_stage_files(self):
        with patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")):
            first = self.run_pipeline()
            before = self.pointer.read_bytes()
            dataset = load_active_dataset(self.run_root, self.pointer)
            artifact_bytes = {p.name: p.read_bytes() for p in dataset.directory.iterdir()}
            second = self.run_pipeline()
        self.assertEqual((first["outcome"], second["outcome"]), ("success", "success"))
        self.assertTrue(first["artifacts_published"])
        self.assertEqual(self.pointer.read_bytes(), before)
        self.assertEqual(artifact_bytes, {p.name: p.read_bytes() for p in dataset.directory.iterdir()})
        self.assertEqual([p.page_number for p in dataset.pages], [1, 2, 3])
        self.assertEqual([c.page_number for c in dataset.chunks], [1, 3])
        for field in ("paper_catalog_path", "extracted_pages_path"):
            self.assertEqual(self.config.resolve(getattr(self.config, field)).read_bytes(),
                             b"prior independent stage output\n")

    def test_partial_missing_and_no_text_papers_preserve_prior_pointer(self):
        self.run_pipeline()
        prior = self.pointer.read_bytes()
        write_json(self.manifest, [VALID_RECORD, SECOND_RECORD])
        for page_texts in (None, [None]):
            if page_texts is not None:
                write_fixture_pdf(self.root / SECOND_RECORD["source_path"], page_texts)
            result = self.run_pipeline()
            self.assertEqual(result["outcome"], "partial_failure")
            self.assertFalse(result["artifacts_published"])
            self.assertEqual(self.pointer.read_bytes(), prior)
        result = self.run_pipeline(allow_partial=True)
        self.assertTrue(result["artifacts_published"])
        self.assertEqual(result["outcome"], "partial_failure")
        data = load_active_dataset(self.run_root, self.pointer)
        self.assertEqual(data.manifest["excluded_paper_ids"], [SECOND_RECORD["paper_id"]])

    def test_total_missing_empty_and_no_text_never_publish(self):
        self.run_pipeline()
        prior = self.pointer.read_bytes()
        for records, texts in (([], None), ([SECOND_RECORD], None), ([VALID_RECORD], [None])):
            write_json(self.manifest, records)
            if texts is not None:
                write_fixture_pdf(self.root / VALID_RECORD["source_path"], texts)
            result = self.run_pipeline(allow_partial=True)
            self.assertEqual(result["outcome"], "failure")
            self.assertIsNone(result["storage_round_trip_valid"])
            self.assertFalse(result["artifacts_published"])
            self.assertEqual(self.pointer.read_bytes(), prior)

    def test_source_mutation_during_extraction_is_rejected(self):
        self.run_pipeline()
        prior = self.pointer.read_bytes()
        original = self.api.extract_manifest_pages
        def changed_source(config):
            report = original(config)
            path = self.root / VALID_RECORD["source_path"]
            path.write_bytes(path.read_bytes() + b"\nchanged")
            return report
        with patch.object(self.api, "extract_manifest_pages", changed_source):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.run_pipeline()
        self.assertEqual(self.pointer.read_bytes(), prior)

    def test_stage_and_serialization_failures_preserve_active_generation(self):
        self.run_pipeline()
        prior = self.pointer.read_bytes()
        for function in ("build_paper_catalog", "extract_manifest_pages", "build_chunks", "write_jsonl"):
            with self.subTest(function=function):
                with patch.object(self.api, function, side_effect=OSError("injected failure")):
                    with self.assertRaises(OSError):
                        self.run_pipeline()
                self.assertEqual(self.pointer.read_bytes(), prior)
                load_active_dataset(self.run_root, self.pointer)

    def test_input_output_aliases_are_rejected_before_any_write(self):
        original = self.manifest.read_bytes()
        for changes in ({"pointer_path": self.manifest}, {"run_root": self.root / "data"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.run_pipeline(**changes)
        self.assertEqual(self.manifest.read_bytes(), original)
        alias = self.root / "alias.json"
        alias.hardlink_to(self.manifest)
        with self.assertRaises(ValueError):
            self.run_pipeline(pointer_path=alias)

    def test_standalone_chunking_consumes_pages_without_reparsing_pdfs(self):
        source_path = self.config.resolve(self.config.extracted_pages_path)
        write_jsonl(source_path, [page().to_dict()])
        source_bytes = source_path.read_bytes()
        result = self.api.run_chunking(self.config, ChunkingConfig())
        self.assertTrue(result["artifacts_published"])
        self.assertEqual(source_path.read_bytes(), source_bytes)
        dataset = load_active_dataset(self.run_root, self.pointer)
        self.assertEqual(dataset.manifest["provenance"]["input_mode"], "existing_pages")
        self.assertNotIn("pdf:" + VALID_RECORD["paper_id"], dataset.manifest["provenance"]["source_hashes"])

    def test_standalone_missing_paper_requires_partial_flag_and_bad_pages_never_publish(self):
        self.run_pipeline()
        prior = self.pointer.read_bytes()
        write_json(self.manifest, [VALID_RECORD, SECOND_RECORD])
        source_path = self.config.resolve(self.config.extracted_pages_path)
        write_jsonl(source_path, [page().to_dict()])
        result = self.api.run_chunking(self.config, ChunkingConfig())
        self.assertEqual(result["outcome"], "partial_failure")
        self.assertEqual(self.pointer.read_bytes(), prior)
        result = self.api.run_chunking(self.config, ChunkingConfig(), allow_partial=True)
        self.assertTrue(result["artifacts_published"])
        selected = self.pointer.read_bytes()
        write_jsonl(source_path, [page().to_dict(), page().to_dict()])
        with self.assertRaises(ValueError):
            self.api.run_chunking(self.config, ChunkingConfig(), allow_partial=True)
        self.assertEqual(self.pointer.read_bytes(), selected)

    def test_partial_report_distinguishes_missing_corrupt_and_zero_page_papers(self):
        corrupt = {**SECOND_RECORD, "paper_id": "2608.20319v1",
                   "pdf_url": "https://arxiv.org/pdf/2608.20319v1", "source_path": "data/corrupt.pdf"}
        empty = {**SECOND_RECORD, "paper_id": "2608.20320v1",
                 "pdf_url": "https://arxiv.org/pdf/2608.20320v1", "source_path": "data/zero.pdf"}
        write_json(self.manifest, [VALID_RECORD, SECOND_RECORD, corrupt, empty])
        (self.root / corrupt["source_path"]).write_bytes(b"not a PDF")
        write_fixture_pdf(self.root / empty["source_path"], [])
        report = self.run_pipeline(allow_partial=True)
        self.assertEqual(report["source_failures"], {
            "missing_pdfs": [SECOND_RECORD["paper_id"]],
            "parsing_failures": [corrupt["paper_id"]],
            "papers_without_usable_text": [empty["paper_id"]], "missing_page_papers": []})
        self.assertNotIn(str(self.root), str(report))
        data = load_active_dataset(self.run_root, self.pointer)
        from research_pipeline.storage import read_json
        self.assertEqual(read_json(data.directory / "quality_report.json")["source_failures"],
                         report["source_failures"])
        manifest = read_json(data.directory / "run_manifest.json")
        del manifest["provenance"]["source_hashes"]["pdf:" + corrupt["paper_id"]]
        write_json(data.directory / "run_manifest.json", manifest)
        from research_pipeline.datasets import load_generation
        with self.assertRaisesRegex(ValueError, "source hash"):
            load_generation(data.directory)

    def test_zero_byte_missing_pdf_can_publish_explicit_partial_data(self):
        write_json(self.manifest, [VALID_RECORD, SECOND_RECORD])
        path = self.root / SECOND_RECORD["source_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        result = self.run_pipeline(allow_partial=True)
        self.assertEqual(result["outcome"], "partial_failure")
        self.assertEqual(result["source_failures"]["missing_pdfs"], [SECOND_RECORD["paper_id"]])
        self.assertTrue(result["artifacts_published"])
        load_active_dataset(self.run_root, self.pointer)


if __name__ == "__main__":
    unittest.main()
