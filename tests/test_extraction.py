"""Stage 2 page preservation, cleanup, and failure reporting tests."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_pipeline.config import PipelineConfig
from research_pipeline.extraction import clean_extracted_text, extract_manifest_pages
from research_pipeline.extraction_cli import run_extract
from research_pipeline.models import ExtractedPage
from research_pipeline.outcomes import FAILURE, PARTIAL_FAILURE, SUCCESS
from research_pipeline.storage import read_jsonl, write_json
from tests.test_ingestion import VALID_RECORD


class FakePage:
    def __init__(self, text: str | None) -> None:
        self.text = text

    def extract_text(self) -> str | None:
        return self.text


class FakeReader:
    def __init__(self, texts: list[str | None]) -> None:
        self.pages = [FakePage(text) for text in texts]


class ExtractionTests(unittest.TestCase):
    def test_later_page_failure_discards_all_pages_from_that_paper(self) -> None:
        class BrokenPage:
            def extract_text(self):
                raise ValueError("later page cannot be parsed")

        class BrokenReader:
            pages = [FakePage("first page is readable"), BrokenPage()]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "manifest.json", [VALID_RECORD])
            pdf_path = root / VALID_RECORD["source_path"]
            pdf_path.parent.mkdir(parents=True)
            pdf_path.write_bytes(b"fixture")
            config = PipelineConfig(repository_root=root, manifest_path=Path("manifest.json"))
            report = extract_manifest_pages(config, reader_factory=lambda _: BrokenReader())
            self.assertEqual(report.outcome, FAILURE)
            self.assertEqual(report.pages_extracted, 0)
            self.assertEqual(report.papers_succeeded, 0)
            self.assertEqual(report.parsing_failures, {"2608.20316v1": "later page cannot be parsed"})
            self.assertEqual(config.resolve(config.extracted_pages_path).read_bytes(), b"")

    def test_cleanup_is_conservative(self) -> None:
        raw = "  first  line\r\n\r\n\r\nsecond-\nline\u00a0value\x00  "
        self.assertEqual(clean_extracted_text(raw), "first line\n\nsecond-\nline value")

    def test_page_numbers_and_empty_pages_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "manifest.json", [VALID_RECORD])
            pdf_path = root / VALID_RECORD["source_path"]
            pdf_path.parent.mkdir(parents=True)
            pdf_path.write_bytes(b"fixture")
            config = PipelineConfig(
                repository_root=root,
                manifest_path=Path("manifest.json"),
                extracted_pages_path=Path("processed/pages.jsonl"),
            )

            report = extract_manifest_pages(
                config, reader_factory=lambda _: FakeReader(["page one", None, "page three"])
            )
            pages = read_jsonl(root / "processed/pages.jsonl", ExtractedPage.from_dict)

            self.assertEqual([page.page_number for page in pages], [1, 2, 3])
            self.assertEqual(pages[1].text, "")
            self.assertEqual(report.pages_extracted, 3)
            self.assertEqual(report.empty_pages, [{"paper_id": "2608.20316v1", "page_number": 2}])
            self.assertEqual(report.outcome, SUCCESS)
            self.assertEqual(report.papers_succeeded, 1)
            self.assertEqual(report.papers_without_usable_text, [])

    def test_mixed_usable_and_empty_papers_report_partial_failure(self) -> None:
        second_record = {
            **VALID_RECORD,
            "paper_id": "2608.20318v1",
            "pdf_url": "https://arxiv.org/pdf/2608.20318v1",
            "source_path": "data/empty.pdf",
        }
        for empty_texts in ([None, " \t"], []):
            with self.subTest(empty_texts=empty_texts), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                write_json(root / "manifest.json", [VALID_RECORD, second_record])
                for record in (VALID_RECORD, second_record):
                    pdf_path = root / record["source_path"]
                    pdf_path.parent.mkdir(parents=True, exist_ok=True)
                    pdf_path.write_bytes(b"fixture")
                config = PipelineConfig(repository_root=root, manifest_path=Path("manifest.json"))
                report = extract_manifest_pages(
                    config,
                    reader_factory=lambda path: FakeReader(
                        empty_texts if path.name == "empty.pdf" else ["usable", None, "last page"]
                    ),
                )
                self.assertEqual(report.outcome, PARTIAL_FAILURE)
                self.assertEqual(report.papers_succeeded, 1)
                self.assertEqual(report.to_dict()["papers_without_usable_text"], [second_record["paper_id"]])
                pages = read_jsonl(config.resolve(config.extracted_pages_path), ExtractedPage.from_dict)
                usable_paper_pages = [page for page in pages if page.paper_id == VALID_RECORD["paper_id"]]
                self.assertEqual([page.page_number for page in usable_paper_pages], [1, 2, 3])
                self.assertEqual(usable_paper_pages[1].text, "")
                empty_paper_pages = [page for page in pages if page.paper_id == second_record["paper_id"]]
                self.assertEqual(len(empty_paper_pages), len(empty_texts))
                self.assertTrue(all(page.text == "" for page in empty_paper_pages))

    def test_paper_without_usable_text_fails_including_zero_page_pdf(self) -> None:
        for texts in ([None, " \t"], []):
            with self.subTest(texts=texts), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                write_json(root / "manifest.json", [VALID_RECORD])
                pdf_path = root / VALID_RECORD["source_path"]
                pdf_path.parent.mkdir(parents=True)
                pdf_path.write_bytes(b"fixture")
                config = PipelineConfig(repository_root=root, manifest_path=Path("manifest.json"))
                report = extract_manifest_pages(config, reader_factory=lambda _: FakeReader(texts))
                self.assertEqual(report.outcome, FAILURE)
                self.assertEqual(report.papers_succeeded, 0)
                self.assertEqual(report.papers_without_usable_text, [VALID_RECORD["paper_id"]])
                self.assertEqual(report.pages_extracted, len(texts))

    def test_standalone_extraction_preserves_previous_pages_unless_partial_allowed(self) -> None:
        second_record = {
            **VALID_RECORD,
            "paper_id": "2608.20318v1",
            "pdf_url": "https://arxiv.org/pdf/2608.20318v1",
            "source_path": "data/empty.pdf",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "manifest.json", [VALID_RECORD, second_record])
            for record in (VALID_RECORD, second_record):
                path = root / record["source_path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture")
            config = PipelineConfig(repository_root=root, manifest_path=Path("manifest.json"))
            pages_path = config.resolve(config.extracted_pages_path)
            pages_path.parent.mkdir(parents=True, exist_ok=True)
            previous = b"previous usable page records\n"
            pages_path.write_bytes(previous)

            def extract_fixture(staged_config: PipelineConfig):
                return extract_manifest_pages(
                    staged_config,
                    reader_factory=lambda path: FakeReader(
                        [None, ""] if path.name == "empty.pdf" else ["usable text"]
                    ),
                )

            with patch("research_pipeline.extraction_cli.extract_manifest_pages", side_effect=extract_fixture):
                report, published = run_extract(config)
                self.assertEqual(report.outcome, PARTIAL_FAILURE)
                self.assertFalse(published)
                self.assertEqual(pages_path.read_bytes(), previous)
                report, published = run_extract(config, allow_partial=True)
                self.assertEqual(report.outcome, PARTIAL_FAILURE)
                self.assertTrue(published)
                pages = read_jsonl(pages_path, ExtractedPage.from_dict)
                self.assertEqual([page.page_number for page in pages if not page.text], [1, 2])

    def test_missing_and_failed_pdfs_are_reported_without_partial_pages(self) -> None:
        second_record = {
            **VALID_RECORD,
            "paper_id": "2608.20318v1",
            "paper_version": "v1",
            "pdf_url": "https://arxiv.org/pdf/2608.20318v1",
            "source_path": "data/broken.pdf",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "manifest.json", [VALID_RECORD, second_record])
            broken_path = root / second_record["source_path"]
            broken_path.parent.mkdir(parents=True)
            broken_path.write_bytes(b"broken")
            config = PipelineConfig(
                repository_root=root,
                manifest_path=Path("manifest.json"),
                extracted_pages_path=Path("processed/pages.jsonl"),
            )

            def failing_reader(_: Path) -> FakeReader:
                raise ValueError("cannot parse fixture")

            report = extract_manifest_pages(config, reader_factory=failing_reader)
            self.assertEqual(report.missing_pdfs, ["2608.20316v1"])
            self.assertEqual(report.parsing_failures, {"2608.20318v1": "cannot parse fixture"})
            self.assertEqual((root / "processed/pages.jsonl").read_text(), "")


if __name__ == "__main__":
    unittest.main()
