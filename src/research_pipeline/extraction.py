"""Page-level PDF extraction with conservative, traceable text cleanup."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, Callable

from research_pipeline.config import PipelineConfig
from research_pipeline.ingestion import load_manifest
from research_pipeline.models import ExtractedPage, PaperMetadata
from research_pipeline.outcomes import FAILURE, PARTIAL_FAILURE, SUCCESS
from research_pipeline.storage import write_jsonl


@dataclass
class ExtractionReport:
    """Observed extraction counts and paper/page-level failures.

    ``papers_succeeded`` counts papers with at least one non-empty cleaned page.
    Parsed papers with no usable text are identified separately, including PDFs
    containing no pages. Blank pages are still retained in the page records.
    """

    outcome: str = SUCCESS
    papers_attempted: int = 0
    papers_succeeded: int = 0
    pages_extracted: int = 0
    empty_pages: list[dict[str, object]] = field(default_factory=list)
    missing_pdfs: list[str] = field(default_factory=list)
    parsing_failures: dict[str, str] = field(default_factory=dict)
    papers_without_usable_text: list[str] = field(default_factory=list)
    extracted_characters: int = 0

    def to_dict(self) -> dict[str, object]:
        """Return JSON-ready counts, original blank-page positions, and errors."""

        return {
            "outcome": self.outcome,
            "papers_attempted": self.papers_attempted,
            "papers_succeeded": self.papers_succeeded,
            "pages_extracted": self.pages_extracted,
            "empty_page_count": len(self.empty_pages),
            "empty_pages": self.empty_pages,
            "missing_pdfs": self.missing_pdfs,
            "parsing_failures": self.parsing_failures,
            "papers_without_usable_text": self.papers_without_usable_text,
            "extracted_characters": self.extracted_characters,
            "usable_page_count": self.pages_extracted - len(self.empty_pages),
        }


def clean_extracted_text(text: str | None) -> str:
    """Apply only layout-safe cleanup and preserve meaningful line boundaries.

    The cleaner removes NUL characters, normalizes line endings and non-breaking
    spaces, trims horizontal whitespace, and limits blank-line runs. It does not
    dehyphenate, reorder columns, remove headers, or infer table/equation content.
    """

    if not text:
        return ""
    normalized = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\u00a0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.split("\n")]
    cleaned_lines: list[str] = []
    previous_was_blank = False
    for line in lines:
        is_blank = not line
        if is_blank and previous_was_blank:
            continue
        cleaned_lines.append(line)
        previous_was_blank = is_blank
    return "\n".join(cleaned_lines).strip()


def _default_reader(pdf_path: Path) -> Any:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError("pypdf is required; install dependencies with pip install -r requirements.txt") from error
    return PdfReader(pdf_path, strict=False)


def _extract_paper_pages(
    paper: PaperMetadata,
    pdf_path: Path,
    reader_factory: Callable[[Path], Any],
) -> list[ExtractedPage]:
    """Extract all pages for one paper or raise its parsing failure."""

    reader = reader_factory(pdf_path)
    pages: list[ExtractedPage] = []
    for page_number, pdf_page in enumerate(reader.pages, start=1):
        raw_text = pdf_page.extract_text()
        pages.append(
            ExtractedPage(
                paper_id=paper.paper_id,
                paper_version=paper.paper_version,
                title=paper.title,
                authors=paper.authors,
                published=paper.published,
                pdf_url=paper.pdf_url,
                page_number=page_number,
                text=clean_extracted_text(raw_text),
            )
        )
    return pages


def extract_manifest_pages(
    config: PipelineConfig,
    reader_factory: Callable[[Path], Any] = _default_reader,
) -> ExtractionReport:
    """Extract manifest PDFs and write their page JSONL to the configured path.

    Args:
        config: Manifest, repository root, and page-output locations.
        reader_factory: PDF reader constructor; defaults to pypdf. Tests can
            inject a reader exposing pages with an extract_text method.

    Returns:
        Counts and per-paper failures. Missing/unparseable papers are skipped;
        no partial pages are retained from a paper that fails midway. Blank
        pages keep their original 1-based PDF positions and empty text. A paper
        with no usable text is incomplete, even if another paper succeeds.

    Raises:
        ValueError: The manifest is malformed.
        OSError: Manifest/output filesystem operations fail.

    This low-level function writes even partial or empty results. Call
    extraction_cli.run_extract for staged, outcome-aware output preservation.
    """

    papers = load_manifest(config.resolve(config.manifest_path))
    report = ExtractionReport(papers_attempted=len(papers))
    extracted_pages: list[ExtractedPage] = []

    for paper in papers:
        pdf_path = config.resolve(Path(paper.source_path))
        if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
            report.missing_pdfs.append(paper.paper_id)
            continue
        try:
            paper_pages = _extract_paper_pages(paper, pdf_path, reader_factory)
        except Exception as error:
            report.parsing_failures[paper.paper_id] = str(error)
            continue

        if any(page.text for page in paper_pages):
            report.papers_succeeded += 1
        else:
            report.papers_without_usable_text.append(paper.paper_id)
        for page in paper_pages:
            if not page.text:
                report.empty_pages.append(
                    {"paper_id": paper.paper_id, "page_number": page.page_number}
                )
            report.extracted_characters += len(page.text)
        report.pages_extracted += len(paper_pages)
        extracted_pages.extend(paper_pages)

    write_jsonl(
        config.resolve(config.extracted_pages_path),
        (page.to_dict() for page in extracted_pages),
    )
    if report.extracted_characters == 0:
        report.outcome = FAILURE
    elif (
        report.missing_pdfs
        or report.parsing_failures
        or report.papers_without_usable_text
        or report.papers_succeeded != report.papers_attempted
    ):
        report.outcome = PARTIAL_FAILURE
    return report
