"""Offline download failures cannot publish truncated source PDFs."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_pipeline.config import PipelineConfig
from research_pipeline.ingestion import collect_arxiv_papers, load_manifest
from research_pipeline.storage import write_json
from tests.test_ingestion import atom_entry


PDF_BYTES = b"%PDF-1.7\ncomplete offline fixture bytes\n%%EOF\n"


class AtomicDownloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = PipelineConfig(repository_root=self.root)
        write_json(self.config.resolve(self.config.manifest_path), [])
        self.pdf_path = self.root / "data/raw/pdfs/2608.20316v1.pdf"

    def fetch(self, url: str) -> bytes:
        return PDF_BYTES if "/pdf/" in url else atom_entry("2608.20316v1")

    def test_interrupted_download_leaves_no_final_file_and_rerun_retries(self) -> None:
        original_write_bytes = Path.write_bytes
        original_temporary_file = tempfile.NamedTemporaryFile

        def interrupted_path_write(path: Path, value: bytes) -> int:
            original_write_bytes(path, value[:8])
            raise OSError("fixture disk full")

        def interrupted_temporary_file(*arguments, **options):
            temporary_file = original_temporary_file(*arguments, **options)
            if arguments and arguments[0] == "wb":
                original_write = temporary_file.write

                def interrupted_write(value: bytes) -> int:
                    original_write(value[:8])
                    raise OSError("fixture disk full")

                temporary_file.write = interrupted_write
            return temporary_file

        # Exercise real file writes in both the old direct-write and new staged paths.
        with patch.object(Path, "write_bytes", interrupted_path_write):
            with patch("research_pipeline.storage.tempfile.NamedTemporaryFile", interrupted_temporary_file):
                first = collect_arxiv_papers(["2608.20316v1"], self.config, True, fetch=self.fetch)
        self.assertEqual(first.outcome, "partial_failure")
        self.assertIn("disk full", first.failures["2608.20316v1"])
        self.assertFalse(self.pdf_path.exists())
        self.assertEqual(list(self.pdf_path.parent.iterdir()), [])
        self.assertEqual(len(load_manifest(self.config.resolve(self.config.manifest_path))), 1)

        second = collect_arxiv_papers(["2608.20316v1"], self.config, True, fetch=self.fetch)
        self.assertEqual(second.outcome, "success")
        self.assertEqual(second.downloaded_pdfs, ["2608.20316v1"])
        self.assertEqual(second.skipped_downloads, [])
        self.assertEqual(self.pdf_path.read_bytes(), PDF_BYTES)

    def test_failed_pdf_replace_preserves_existing_file_and_cleans_temporary(self) -> None:
        self.pdf_path.parent.mkdir(parents=True)
        self.pdf_path.write_bytes(b"")
        original_replace = Path.replace

        def replace(source: Path, destination: Path) -> Path:
            if Path(destination) == self.pdf_path:
                raise PermissionError("fixture PDF publication denied")
            return original_replace(source, destination)

        with patch.object(Path, "replace", replace):
            report = collect_arxiv_papers(["2608.20316v1"], self.config, True, fetch=self.fetch)
        self.assertEqual(report.outcome, "partial_failure")
        self.assertIn("publication denied", report.failures["2608.20316v1"])
        self.assertEqual(self.pdf_path.read_bytes(), b"")
        self.assertEqual(list(self.pdf_path.parent.iterdir()), [self.pdf_path])

    def test_successful_legacy_download_keeps_nested_path_and_skips_on_rerun(self) -> None:
        def fetch(url: str) -> bytes:
            return PDF_BYTES if "/pdf/" in url else atom_entry("hep-th/9901001v1")

        first = collect_arxiv_papers(["hep-th/9901001v1"], self.config, True, fetch=fetch)
        self.assertEqual(first.outcome, "success")
        path = self.root / "data/raw/pdfs/hep-th/9901001v1.pdf"
        self.assertEqual(path.read_bytes(), PDF_BYTES)
        self.assertEqual(list(path.parent.iterdir()), [path])
        second = collect_arxiv_papers(["hep-th/9901001v1"], self.config, True, fetch=fetch)
        self.assertEqual(second.skipped_downloads, ["hep-th/9901001v1"])
        self.assertEqual(path.read_bytes(), PDF_BYTES)


if __name__ == "__main__":
    unittest.main()
