"""Standalone extraction contract checks using real, tiny offline PDFs."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from research_pipeline.config import PipelineConfig
from research_pipeline.extraction_cli import main
from research_pipeline.models import ExtractedPage
from research_pipeline.storage import read_jsonl, write_json
from tests.test_ingestion import VALID_RECORD


SECOND_RECORD = {
    **VALID_RECORD,
    "paper_id": "2608.20318v1",
    "pdf_url": "https://arxiv.org/pdf/2608.20318v1",
    "source_path": "data/second.pdf",
}


def write_fixture_pdf(path: Path, page_texts: list[str | None]) -> None:
    """Write hand-sized real PDFs; None is a blank page and [] has no pages."""

    writer = PdfWriter()
    for text in page_texts:
        page = writer.add_blank_page(width=612, height=792)
        if text is not None:
            font = DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            })
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
            })
            content = DecodedStreamObject()
            content.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
            page.replace_contents(content)
    path.parent.mkdir(parents=True, exist_ok=True)
    writer.write(path)


class ExtractionCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = PipelineConfig(repository_root=self.root)
        self.pages_path = self.config.resolve(self.config.extracted_pages_path)
        self.pages_path.parent.mkdir(parents=True)
        self.previous_pages = b"previous usable pages\n"
        self.pages_path.write_bytes(self.previous_pages)
        self.catalog_path = self.config.resolve(self.config.paper_catalog_path)
        self.catalog_path.write_bytes(b"previous catalog\n")

    def write_manifest(self, records: list[dict]) -> None:
        write_json(self.config.resolve(self.config.manifest_path), records)

    def invoke(self, *arguments: str) -> tuple[int, dict]:
        # Redirect only configuration, not parsing or publication behavior.
        output = io.StringIO()
        with patch("research_pipeline.extraction_cli.PipelineConfig", return_value=self.config):
            with redirect_stdout(output), redirect_stderr(io.StringIO()):
                exit_code = main(list(arguments))
        self.assertEqual(self.catalog_path.read_bytes(), b"previous catalog\n")
        self.assertFalse(list((self.root / "data").glob(".pipeline-staging-*")))
        return exit_code, json.loads(output.getvalue())

    def assert_previous_pages_preserved(self) -> None:
        self.assertEqual(self.pages_path.read_bytes(), self.previous_pages)

    def test_success_publishes_complete_citations_and_keeps_blank_page_position(self) -> None:
        self.write_manifest([VALID_RECORD])
        write_fixture_pdf(self.root / VALID_RECORD["source_path"], ["first page", None, "last page"])
        exit_code, report = self.invoke()
        self.assertEqual(exit_code, 0)
        self.assertEqual(report["outcome"], "success")
        self.assertTrue(report["artifacts_published"])
        self.assertEqual(report["pages_extracted"], 3)
        self.assertEqual(report["empty_pages"], [{"paper_id": "2608.20316v1", "page_number": 2}])
        pages = read_jsonl(self.pages_path, ExtractedPage.from_dict)
        self.assertEqual([page.page_number for page in pages], [1, 2, 3])
        self.assertEqual([page.text for page in pages], ["first page", "", "last page"])
        for page in pages:
            for field_name in ("paper_id", "paper_version", "title", "authors", "published", "pdf_url"):
                self.assertEqual(page.to_dict()[field_name], VALID_RECORD[field_name])

    def test_partial_missing_pdf_preserves_existing_output_by_default(self) -> None:
        self.write_manifest([VALID_RECORD, SECOND_RECORD])
        write_fixture_pdf(self.root / VALID_RECORD["source_path"], ["usable text"])
        exit_code, report = self.invoke()
        self.assertEqual((exit_code, report["outcome"]), (2, "partial_failure"))
        self.assertEqual(report["missing_pdfs"], ["2608.20318v1"])
        self.assertFalse(report["artifacts_published"])
        self.assert_previous_pages_preserved()

    def test_explicit_partial_publication_remains_nonzero(self) -> None:
        self.write_manifest([VALID_RECORD, SECOND_RECORD])
        write_fixture_pdf(self.root / VALID_RECORD["source_path"], ["usable text"])
        exit_code, report = self.invoke("--allow-partial")
        self.assertEqual((exit_code, report["outcome"]), (2, "partial_failure"))
        self.assertTrue(report["artifacts_published"])
        pages = read_jsonl(self.pages_path, ExtractedPage.from_dict)
        self.assertEqual([(page.paper_id, page.text) for page in pages], [("2608.20316v1", "usable text")])

    def test_all_missing_pdfs_never_publish_even_when_partial_is_allowed(self) -> None:
        self.write_manifest([VALID_RECORD])
        for arguments in ((), ("--allow-partial",)):
            with self.subTest(arguments=arguments):
                exit_code, report = self.invoke(*arguments)
                self.assertEqual((exit_code, report["outcome"]), (3, "failure"))
                self.assertFalse(report["artifacts_published"])
                self.assert_previous_pages_preserved()

    def test_partial_and_total_pdf_parsing_failures_preserve_output(self) -> None:
        broken_pdf = self.root / SECOND_RECORD["source_path"]
        broken_pdf.parent.mkdir(parents=True, exist_ok=True)
        broken_pdf.write_bytes(b"not a parseable PDF")
        write_fixture_pdf(self.root / VALID_RECORD["source_path"], ["usable text"])
        for records, expected_exit in (([VALID_RECORD, SECOND_RECORD], 2), ([SECOND_RECORD], 3)):
            with self.subTest(expected_exit=expected_exit):
                self.write_manifest(records)
                exit_code, report = self.invoke()
                self.assertEqual(exit_code, expected_exit)
                self.assertIn("2608.20318v1", report["parsing_failures"])
                self.assertFalse(report["artifacts_published"])
                self.assert_previous_pages_preserved()

    def test_all_blank_and_zero_page_pdfs_never_publish(self) -> None:
        self.write_manifest([VALID_RECORD])
        for page_texts in ([None, None], []):
            with self.subTest(page_texts=page_texts):
                write_fixture_pdf(self.root / VALID_RECORD["source_path"], page_texts)
                exit_code, report = self.invoke("--allow-partial")
                self.assertEqual((exit_code, report["outcome"]), (3, "failure"))
                self.assertEqual(report["papers_succeeded"], 0)
                self.assertEqual(report["papers_without_usable_text"], ["2608.20316v1"])
                self.assertFalse(report["artifacts_published"])
                self.assert_previous_pages_preserved()

    def test_mixed_usable_and_blank_papers_require_explicit_partial_publication(self) -> None:
        self.write_manifest([VALID_RECORD, SECOND_RECORD])
        write_fixture_pdf(self.root / VALID_RECORD["source_path"], ["usable text"])
        write_fixture_pdf(self.root / SECOND_RECORD["source_path"], [None])
        exit_code, report = self.invoke()
        self.assertEqual((exit_code, report["papers_succeeded"]), (2, 1))
        self.assertEqual(report["papers_without_usable_text"], ["2608.20318v1"])
        self.assertFalse(report["artifacts_published"])
        self.assert_previous_pages_preserved()
        exit_code, report = self.invoke("--allow-partial")
        self.assertEqual(exit_code, 2)
        self.assertTrue(report["artifacts_published"])
        pages = read_jsonl(self.pages_path, ExtractedPage.from_dict)
        self.assertEqual([(page.paper_id, page.page_number, page.text) for page in pages],
                         [("2608.20316v1", 1, "usable text"), ("2608.20318v1", 1, "")])

    def test_empty_manifest_reports_failure_and_preserves_output(self) -> None:
        self.write_manifest([])
        exit_code, report = self.invoke()
        self.assertEqual((exit_code, report["outcome"]), (3, "failure"))
        self.assertEqual(report["papers_attempted"], 0)
        self.assertFalse(report["artifacts_published"])
        self.assert_previous_pages_preserved()

    def test_invalid_manifest_returns_failure_without_replacing_output(self) -> None:
        self.write_manifest([{**VALID_RECORD, "authors": []}])
        exit_code, report = self.invoke()
        self.assertEqual((exit_code, report["outcome"]), (3, "failure"))
        self.assertIn("authors", report["error"])
        self.assert_previous_pages_preserved()


class PageContractTests(unittest.TestCase):
    def test_invalid_page_numbers_are_rejected(self) -> None:
        for page_number in (True, False, 0, -1, "1", 1.0, None):
            with self.subTest(page_number=page_number):
                with self.assertRaisesRegex(ValueError, "page_number"):
                    ExtractedPage.from_dict({**VALID_RECORD, "page_number": page_number, "text": "text"})

    def test_blank_text_is_valid_but_nonstring_text_is_rejected(self) -> None:
        page = ExtractedPage.from_dict({**VALID_RECORD, "page_number": 1, "text": ""})
        self.assertEqual(page.text, "")
        for text in (None, 1, ["text"]):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "text must be a string"):
                    ExtractedPage.from_dict({**VALID_RECORD, "page_number": 1, "text": text})


if __name__ == "__main__":
    unittest.main()
