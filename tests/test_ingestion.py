"""Stage 1 manifest and idempotent collection tests."""

from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from research_pipeline.config import PipelineConfig
from research_pipeline.ingestion import (
    _parse_arxiv_entry,
    build_paper_catalog,
    collect_arxiv_papers,
    load_manifest,
)
from research_pipeline.outcomes import FAILURE, PARTIAL_FAILURE, SUCCESS
from research_pipeline.storage import write_json


VALID_RECORD = {
    "paper_id": "2608.20316v1",
    "paper_version": "v1",
    "title": "Fixture Paper",
    "authors": ["A. Author"],
    "published": "2026-08-21",
    "pdf_url": "https://arxiv.org/pdf/2608.20316v1",
    "source_path": "data/fixture.pdf",
}


def atom_entry(paper_id: str, entry_id: str | None = None) -> bytes:
    """Return one small offline Atom response for a modern or legacy ID."""

    identifier = paper_id if entry_id is None else entry_id
    return f"""<feed xmlns="http://www.w3.org/2005/Atom"><entry>
    <id>http://arxiv.org/abs/{identifier}</id>
    <published>2026-08-21T00:00:00Z</published><title>Fixture Paper</title>
    <author><name>A. Author</name></author>
    <link title="pdf" href="http://arxiv.org/pdf/{paper_id}" type="application/pdf"/>
    </entry></feed>""".encode()


class ManifestTests(unittest.TestCase):
    def test_duplicate_paper_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "papers.json"
            write_json(manifest_path, [VALID_RECORD, VALID_RECORD])
            with self.assertRaisesRegex(ValueError, "duplicate paper_id"):
                load_manifest(manifest_path)

    def test_missing_and_invalid_metadata_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "papers.json"
            invalid = {**VALID_RECORD, "authors": [], "published": "August 21"}
            del invalid["title"]
            write_json(manifest_path, [invalid])
            with self.assertRaisesRegex(ValueError, "missing paper metadata fields: title"):
                load_manifest(manifest_path)

    def test_invalid_metadata_values_are_rejected(self) -> None:
        invalid_values = [
            ({**VALID_RECORD, "authors": []}, "authors must be a non-empty list"),
            ({**VALID_RECORD, "published": "August 21"}, "published must use ISO date format"),
            ({**VALID_RECORD, "paper_version": "v2"}, "must match the suffix"),
            ({**VALID_RECORD, "source_path": "../outside.pdf"}, "must be repository-relative"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "papers.json"
            for record, expected_message in invalid_values:
                with self.subTest(expected_message=expected_message):
                    write_json(manifest_path, [record])
                    with self.assertRaisesRegex(ValueError, expected_message):
                        load_manifest(manifest_path)

    def test_catalog_rerun_is_stable_and_reports_missing_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "manifest.json", [VALID_RECORD])
            config = PipelineConfig(
                repository_root=root,
                manifest_path=Path("manifest.json"),
                paper_catalog_path=Path("processed/papers.jsonl"),
            )
            first_report = build_paper_catalog(config)
            first_bytes = (root / "processed/papers.jsonl").read_bytes()
            second_report = build_paper_catalog(config)
            self.assertEqual(first_bytes, (root / "processed/papers.jsonl").read_bytes())
            self.assertEqual(first_report.missing_pdfs, ["2608.20316v1"])
            self.assertEqual(first_report.outcome, FAILURE)
            self.assertEqual(second_report.to_dict(), first_report.to_dict())


class CollectionTests(unittest.TestCase):
    def test_collection_and_download_rerun_do_not_duplicate_or_redownload(self) -> None:
        atom = b"""<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/2608.20316v1</id>
            <published>2026-08-21T00:00:00Z</published>
            <title>Fixture Paper</title>
            <author><name>A. Author</name></author>
            <link title="pdf" href="http://arxiv.org/pdf/2608.20316v1" type="application/pdf"/>
          </entry>
        </feed>"""
        calls: list[str] = []

        def fake_fetch(url: str) -> bytes:
            calls.append(url)
            return b"%PDF-fixture" if "/pdf/" in url else atom

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "manifest.json", [])
            config = PipelineConfig(repository_root=root, manifest_path=Path("manifest.json"))
            first = collect_arxiv_papers(
                ["2608.20316v1"], config, download_pdfs=True, fetch=fake_fetch
            )
            second = collect_arxiv_papers(
                ["2608.20316v1"], config, download_pdfs=True, fetch=fake_fetch
            )

            self.assertEqual(first.added_papers, ["2608.20316v1"])
            self.assertEqual(first.downloaded_pdfs, ["2608.20316v1"])
            self.assertEqual(second.existing_papers, ["2608.20316v1"])
            self.assertEqual(second.skipped_downloads, ["2608.20316v1"])
            self.assertEqual(second.outcome, SUCCESS)
            self.assertEqual(len(load_manifest(root / "manifest.json")), 1)
            self.assertEqual(len(calls), 2)

    def test_versionless_collection_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "manifest.json", [])
            config = PipelineConfig(repository_root=root, manifest_path=Path("manifest.json"))
            with self.assertRaisesRegex(ValueError, "must include a version"):
                collect_arxiv_papers(["2608.20316"], config)

    def test_failed_pdf_download_is_reported_and_metadata_is_retained(self) -> None:
        atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <id>http://arxiv.org/abs/2608.20316v1</id>
        <published>2026-08-21T00:00:00Z</published><title>Fixture Paper</title>
        <author><name>A. Author</name></author>
        <link title="pdf" href="http://arxiv.org/pdf/2608.20316v1" type="application/pdf"/>
        </entry></feed>"""

        def fake_fetch(url: str) -> bytes:
            return b"not a pdf" if "/pdf/" in url else atom

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "manifest.json", [])
            config = PipelineConfig(repository_root=root, manifest_path=Path("manifest.json"))
            report = collect_arxiv_papers(
                ["2608.20316v1"], config, download_pdfs=True, fetch=fake_fetch
            )
            self.assertRegex(report.failures["2608.20316v1"], "response did not begin with a PDF header")
            self.assertEqual(report.outcome, PARTIAL_FAILURE)
            self.assertEqual(len(load_manifest(root / "manifest.json")), 1)


class AtomParsingTests(unittest.TestCase):
    def test_modern_versioned_id_is_preserved(self) -> None:
        paper = _parse_arxiv_entry(
            atom_entry("2608.20316v1"),
            "2608.20316v1",
            "data/raw/pdfs/2608.20316v1.pdf",
        )
        self.assertEqual(paper.paper_id, "2608.20316v1")

    def test_legacy_versioned_id_preserves_category_prefix(self) -> None:
        paper = _parse_arxiv_entry(
            atom_entry("hep-th/9901001v1"),
            "hep-th/9901001v1",
            "data/raw/pdfs/hep-th/9901001v1.pdf",
        )
        self.assertEqual(paper.paper_id, "hep-th/9901001v1")
        self.assertEqual(paper.source_path, "data/raw/pdfs/hep-th/9901001v1.pdf")
        self.assertEqual(paper.pdf_url, "https://arxiv.org/pdf/hep-th/9901001v1")

    def test_different_response_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "arXiv returned 2608.20318v1"):
            _parse_arxiv_entry(
                atom_entry("2608.20316v1", entry_id="2608.20318v1"),
                "2608.20316v1",
                "data/raw/pdfs/2608.20316v1.pdf",
            )

    def test_missing_or_malformed_response_id_is_rejected(self) -> None:
        missing = atom_entry("2608.20316v1").replace(
            b"http://arxiv.org/abs/2608.20316v1", b""
        )
        malformed = atom_entry("2608.20316v1").replace(
            b"http://arxiv.org/abs/2608.20316v1", b"http://arxiv.org/abs/not-an-id"
        )
        for response in (missing, malformed):
            with self.subTest(response=response):
                with self.assertRaisesRegex(ValueError, "entry ID|malformed"):
                    _parse_arxiv_entry(
                        response,
                        "2608.20316v1",
                        "data/raw/pdfs/2608.20316v1.pdf",
                    )


class RequestPacingTests(unittest.TestCase):
    def test_api_attempts_are_at_least_three_seconds_apart_including_failures(self) -> None:
        now = [0.0]
        sleeps: list[float] = []
        attempt_times: list[float] = []

        def clock() -> float:
            return now[0]

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            now[0] += seconds

        def fetch(url: str) -> bytes:
            attempt_times.append(clock())
            paper_id = parse_qs(urlsplit(url).query)["id_list"][0]
            if paper_id == "2608.20316v1":
                raise OSError("offline fixture failure")
            return atom_entry(paper_id)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "manifest.json", [])
            config = PipelineConfig(repository_root=root, manifest_path=Path("manifest.json"))
            report = collect_arxiv_papers(
                ["2608.20316v1", "2608.20318v1", "2608.20319v1"],
                config,
                fetch=fetch,
                clock=clock,
                sleep=sleep,
            )
        self.assertEqual(attempt_times, [0.0, 3.0, 6.0])
        self.assertEqual(sleeps, [3.0, 3.0])
        self.assertEqual(report.outcome, PARTIAL_FAILURE)

    def test_existing_record_is_skipped_without_sleeping(self) -> None:
        now = [0.0]
        sleeps: list[float] = []
        attempt_times: list[float] = []

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            now[0] += seconds

        def fetch(url: str) -> bytes:
            attempt_times.append(now[0])
            paper_id = parse_qs(urlsplit(url).query)["id_list"][0]
            return atom_entry(paper_id)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "manifest.json", [VALID_RECORD])
            config = PipelineConfig(repository_root=root, manifest_path=Path("manifest.json"))
            collect_arxiv_papers(
                ["2608.20316v1", "2608.20318v1"],
                config,
                fetch=fetch,
                clock=lambda: now[0],
                sleep=sleep,
            )
        self.assertEqual(attempt_times, [0.0])
        self.assertEqual(sleeps, [])


if __name__ == "__main__":
    unittest.main()
