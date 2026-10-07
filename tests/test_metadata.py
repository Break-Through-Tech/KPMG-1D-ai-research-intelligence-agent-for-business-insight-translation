"""Citation identity checks for manifest records and arXiv responses."""

from pathlib import Path
import tempfile
import unittest

from research_pipeline.config import PipelineConfig

from research_pipeline.ingestion import _parse_arxiv_entry, collect_arxiv_papers
from research_pipeline.models import PaperMetadata
from research_pipeline.storage import write_json
from tests.test_ingestion import VALID_RECORD, atom_entry


class CitationUrlTests(unittest.TestCase):
    def test_pdf_url_must_identify_the_declared_paper_and_version(self) -> None:
        invalid_urls = (
            "https://arxiv.org/pdf/2608.20318v2",
            "https://arxiv.org/pdf/2608.20316v2",
            "https://arxiv.org/pdf/2608.20316",
            "https://arxiv.org/pdf/",
            "https://arxiv.org/pdf/2608.20316v1/extra",
            "https://arxiv.org/pdf/2608.20316v1?download=other",
            "https://arxiv.org/pdf/2608.20316v1#other",
            "https://arxiv.org.evil.invalid/pdf/2608.20316v1",
            "https://user@arxiv.org/pdf/2608.20316v1",
        )
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaisesRegex(ValueError, "pdf_url"):
                    PaperMetadata.from_dict({**VALID_RECORD, "pdf_url": url})

    def test_same_version_modern_and_legacy_pdf_urls_are_accepted(self) -> None:
        for paper_id in ("2608.20316v1", "hep-th/9901001v1", "cs.LG/9901001v1"):
            for suffix in ("", ".pdf"):
                for scheme in ("http", "https"):
                    url = f"{scheme}://arxiv.org/pdf/{paper_id}{suffix}"
                    with self.subTest(url=url):
                        paper = PaperMetadata.from_dict({
                            **VALID_RECORD, "paper_id": paper_id, "pdf_url": url,
                        })
                        self.assertEqual(paper.paper_id, paper_id)
                        self.assertEqual(paper.pdf_url, url)

    def test_atom_pdf_link_mismatch_is_rejected(self) -> None:
        for pdf_id in ("2608.20318v1", "2608.20316v2", "2608.20316", ""):
            response = atom_entry("2608.20316v1").replace(
                b"http://arxiv.org/pdf/2608.20316v1",
                f"http://arxiv.org/pdf/{pdf_id}".encode(),
            )
            with self.subTest(pdf_id=pdf_id):
                with self.assertRaisesRegex(ValueError, "pdf_url"):
                    _parse_arxiv_entry(response, "2608.20316v1", "data/fixture.pdf")


class PublicationDateTests(unittest.TestCase):
    def test_only_canonical_calendar_dates_are_accepted(self) -> None:
        for published in ("20260821", "2026-W34-5", "2026-8-21", "2026-02-30"):
            with self.subTest(published=published):
                with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
                    PaperMetadata.from_dict({**VALID_RECORD, "published": published})
        paper = PaperMetadata.from_dict({**VALID_RECORD, "published": "2024-02-29"})
        self.assertEqual(paper.published, "2024-02-29")


class IdentifierCasingTests(unittest.TestCase):
    def test_noncanonical_manifest_ids_are_rejected(self) -> None:
        for paper_id in ("2608.20316V1", "HEP-TH/9901001v1", "cs.lg/9901001v1"):
            with self.subTest(paper_id=paper_id):
                with self.assertRaisesRegex(ValueError, "paper_id"):
                    PaperMetadata.from_dict({
                        **VALID_RECORD,
                        "paper_id": paper_id,
                        "pdf_url": f"https://arxiv.org/pdf/{paper_id}",
                    })

    def test_noncanonical_requested_ids_fail_before_fetch_or_manifest_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            write_json(manifest_path, [VALID_RECORD])
            original = manifest_path.read_bytes()
            config = PipelineConfig(repository_root=root, manifest_path=Path("manifest.json"))
            requests = []

            def fetch(url: str) -> bytes:
                requests.append(url)
                return atom_entry("2608.20316v1")

            for paper_id in ("2608.20316V1", "HEP-TH/9901001v1", "2608.20316v0"):
                with self.subTest(paper_id=paper_id):
                    with self.assertRaisesRegex(ValueError, "arXiv ID"):
                        collect_arxiv_papers([paper_id], config, fetch=fetch)
                    self.assertEqual(manifest_path.read_bytes(), original)
                    self.assertEqual(requests, [])


if __name__ == "__main__":
    unittest.main()
