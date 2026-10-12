"""Prevent one local PDF from being attributed to different paper identities."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_pipeline.config import PipelineConfig
from research_pipeline.extraction_cli import main as extract_main
from research_pipeline.ingestion import collect_arxiv_papers, load_manifest, save_manifest
from research_pipeline.ingestion_cli import main as ingest_main
from research_pipeline.models import PaperMetadata
from research_pipeline.storage import write_json
from tests.test_ingestion import VALID_RECORD, atom_entry


SECOND_RECORD = {
    **VALID_RECORD,
    "paper_id": "2608.20318v1",
    "title": "Different paper",
    "pdf_url": "https://arxiv.org/pdf/2608.20318v1",
}


class ManifestPathTests(unittest.TestCase):
    def test_existing_case_aliases_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "data/fixture.pdf"
            source.parent.mkdir()
            source.write_bytes(b"%PDF-source")
            alias = root / "data/FIXTURE.pdf"
            if not alias.exists() or not source.samefile(alias):
                self.skipTest("filesystem has case-sensitive names")
            manifest_path = root / "manifest.json"
            write_json(manifest_path, [VALID_RECORD, {**SECOND_RECORD, "source_path": "data/FIXTURE.pdf"}])
            with self.assertRaisesRegex(ValueError, "source_path"):
                load_manifest(manifest_path, root)

    def test_existing_hardlink_aliases_are_rejected_on_load_and_save(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "data/fixture.pdf"
            source.parent.mkdir()
            source.write_bytes(b"%PDF-source")
            os.link(source, root / "data/alias.pdf")
            records = [VALID_RECORD, {**SECOND_RECORD, "source_path": "data/alias.pdf"}]
            manifest_path = root / "manifest.json"
            write_json(manifest_path, records)
            with self.assertRaisesRegex(ValueError, "source_path"):
                load_manifest(manifest_path, root)
            previous = manifest_path.read_bytes()
            with self.assertRaisesRegex(ValueError, "source_path"):
                save_manifest(manifest_path, [PaperMetadata.from_dict(record) for record in records], root)
            self.assertEqual(manifest_path.read_bytes(), previous)

    def test_existing_symlink_aliases_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "data/fixture.pdf"
            source.parent.mkdir()
            source.write_bytes(b"%PDF-source")
            (root / "data/alias.pdf").symlink_to("fixture.pdf")
            manifest_path = root / "manifest.json"
            write_json(manifest_path, [VALID_RECORD, {**SECOND_RECORD, "source_path": "data/alias.pdf"}])
            with self.assertRaisesRegex(ValueError, "source_path"):
                load_manifest(manifest_path, root)

    def test_distinct_files_with_equal_bytes_are_not_identity_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data").mkdir()
            (root / "data/fixture.pdf").write_bytes(b"%PDF-same-fixture")
            (root / "data/second.pdf").write_bytes(b"%PDF-same-fixture")
            manifest_path = root / "manifest.json"
            write_json(manifest_path, [VALID_RECORD, {**SECOND_RECORD, "source_path": "data/second.pdf"}])
            papers = load_manifest(manifest_path, root)
            self.assertEqual([paper.paper_id for paper in papers], ["2608.20316v1", "2608.20318v1"])

    def test_load_rejects_duplicate_and_normalized_source_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.json"
            for source_path in ("data/fixture.pdf", "data/./fixture.pdf", "data//fixture.pdf"):
                with self.subTest(source_path=source_path):
                    write_json(manifest_path, [VALID_RECORD, {**SECOND_RECORD, "source_path": source_path}])
                    with self.assertRaisesRegex(ValueError, "source_path"):
                        load_manifest(manifest_path)

    def test_save_rejects_path_collision_without_replacing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.json"
            write_json(manifest_path, [VALID_RECORD])
            previous = manifest_path.read_bytes()
            papers = [PaperMetadata.from_dict(record) for record in (VALID_RECORD, SECOND_RECORD)]
            with self.assertRaisesRegex(ValueError, "source_path"):
                save_manifest(manifest_path, papers)
            self.assertEqual(manifest_path.read_bytes(), previous)

    def test_both_clis_reject_shared_pdf_before_replacing_prior_output(self) -> None:
        for main, module, output_field, arguments in (
            (ingest_main, "ingestion_cli", "paper_catalog_path", ["ingest"]),
            (extract_main, "extraction_cli", "extracted_pages_path", []),
        ):
            with self.subTest(module=module), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = PipelineConfig(repository_root=root)
                write_json(config.resolve(config.manifest_path), [VALID_RECORD, SECOND_RECORD])
                pdf_path = root / VALID_RECORD["source_path"]
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                pdf_path.write_bytes(b"%PDF-fixture")
                output_path = config.resolve(getattr(config, output_field))
                output_path.parent.mkdir(parents=True)
                output_path.write_bytes(b"previous artifact\n")
                stdout = io.StringIO()
                with patch(f"research_pipeline.{module}.PipelineConfig", return_value=config):
                    with redirect_stdout(stdout):
                        exit_code = main(arguments)
                self.assertEqual(exit_code, 3)
                self.assertIn("source_path", json.loads(stdout.getvalue()).get("error", ""))
                self.assertEqual(output_path.read_bytes(), b"previous artifact\n")
                self.assertFalse(list((root / "data").glob(".pipeline-staging-*")))

    def test_collection_rejects_existing_collision_before_any_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = PipelineConfig(repository_root=root)
            manifest_path = config.resolve(config.manifest_path)
            write_json(manifest_path, [VALID_RECORD, SECOND_RECORD])
            original = manifest_path.read_bytes()
            requests = []

            def fetch(url: str) -> bytes:
                requests.append(url)
                return atom_entry("2608.20316v1")

            with self.assertRaisesRegex(ValueError, "source_path"):
                collect_arxiv_papers(["2608.20316v1"], config, True, fetch=fetch)
            self.assertEqual(requests, [])
            self.assertEqual(manifest_path.read_bytes(), original)
            self.assertFalse(config.resolve(config.downloaded_pdf_directory).exists())

    def test_newly_collected_identity_cannot_claim_an_existing_pdf_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = PipelineConfig(repository_root=root)
            shared_path = "data/raw/pdfs/2608.20318v1.pdf"
            write_json(config.resolve(config.manifest_path), [{**VALID_RECORD, "source_path": shared_path}])
            pdf_path = root / shared_path
            pdf_path.parent.mkdir(parents=True)
            pdf_path.write_bytes(b"%PDF-original-paper")

            def fetch(url: str) -> bytes:
                return atom_entry("2608.20318v1")

            report = collect_arxiv_papers(["2608.20318v1"], config, True, fetch=fetch)
            self.assertEqual(report.outcome, "failure")
            self.assertIn("source_path", report.failures["2608.20318v1"])
            self.assertEqual(report.added_papers, [])
            self.assertEqual(pdf_path.read_bytes(), b"%PDF-original-paper")
            self.assertEqual([paper.paper_id for paper in load_manifest(config.resolve(config.manifest_path))],
                             ["2608.20316v1"])


if __name__ == "__main__":
    unittest.main()
