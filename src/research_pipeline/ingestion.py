"""Reproducible manifest validation and opt-in arXiv metadata/PDF collection."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import time
from typing import Callable
from urllib.parse import unquote, urlencode, urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ElementTree

from research_pipeline.config import PipelineConfig
from research_pipeline.models import ARXIV_ID_PATTERN, PaperMetadata
from research_pipeline.outcomes import FAILURE, PARTIAL_FAILURE, SUCCESS
from research_pipeline.storage import read_json, write_json, write_jsonl


ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_MIN_REQUEST_INTERVAL_SECONDS = 3.0
USER_AGENT = "kpmg-research-pipeline/1.0 (student prototype)"


@dataclass
class IngestionReport:
    """Counts and actionable failures from one ingestion or collection run."""

    outcome: str = SUCCESS
    requested_papers: int = 0
    manifest_papers: int = 0
    available_pdfs: int = 0
    missing_pdfs: list[str] = field(default_factory=list)
    added_papers: list[str] = field(default_factory=list)
    existing_papers: list[str] = field(default_factory=list)
    downloaded_pdfs: list[str] = field(default_factory=list)
    skipped_downloads: list[str] = field(default_factory=list)
    failures: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "outcome": self.outcome,
            "requested_papers": self.requested_papers,
            "manifest_papers": self.manifest_papers,
            "available_pdfs": self.available_pdfs,
            "missing_pdfs": self.missing_pdfs,
            "added_papers": self.added_papers,
            "existing_papers": self.existing_papers,
            "downloaded_pdfs": self.downloaded_pdfs,
            "skipped_downloads": self.skipped_downloads,
            "failures": self.failures,
        }


def load_manifest(path: Path) -> list[PaperMetadata]:
    """Load a JSON paper manifest and reject duplicate versioned paper IDs."""

    raw_records = read_json(path)
    if not isinstance(raw_records, list):
        raise ValueError("paper manifest must be a JSON list")
    papers = [PaperMetadata.from_dict(record) for record in raw_records]
    paper_ids = [paper.paper_id for paper in papers]
    duplicates = sorted({paper_id for paper_id in paper_ids if paper_ids.count(paper_id) > 1})
    if duplicates:
        raise ValueError(f"duplicate paper_id values in manifest: {', '.join(duplicates)}")
    return papers


def save_manifest(path: Path, papers: list[PaperMetadata]) -> None:
    """Save one stable, paper-ID-sorted manifest record per paper."""

    unique: dict[str, PaperMetadata] = {}
    for paper in papers:
        if paper.paper_id in unique:
            raise ValueError(f"duplicate paper_id cannot be saved: {paper.paper_id}")
        unique[paper.paper_id] = paper
    write_json(path, [unique[paper_id].to_dict() for paper_id in sorted(unique)])


def build_paper_catalog(config: PipelineConfig) -> IngestionReport:
    """Validate the fixed manifest, locate PDFs, and write retrieval-ready metadata."""

    manifest_path = config.resolve(config.manifest_path)
    papers = load_manifest(manifest_path)
    report = IngestionReport(manifest_papers=len(papers), requested_papers=len(papers))
    catalog_records: list[dict[str, object]] = []

    for paper in papers:
        source_path = config.resolve(Path(paper.source_path))
        if source_path.is_file() and source_path.stat().st_size > 0:
            report.available_pdfs += 1
        else:
            report.missing_pdfs.append(paper.paper_id)
        catalog_records.append(paper.to_dict())

    write_jsonl(config.resolve(config.paper_catalog_path), catalog_records)
    if report.available_pdfs == 0:
        report.outcome = FAILURE
    elif report.missing_pdfs:
        report.outcome = PARTIAL_FAILURE
    return report


@dataclass
class ArxivRequestPacer:
    """Enforce a minimum start-time interval between sequential API attempts."""

    minimum_interval_seconds: float = ARXIV_MIN_REQUEST_INTERVAL_SECONDS
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    _last_attempt_started_at: float | None = field(default=None, init=False)

    def wait_for_next_attempt(self) -> None:
        """Wait if needed, then record this request attempt's start time."""

        now = self.clock()
        if self._last_attempt_started_at is not None:
            remaining = self.minimum_interval_seconds - (now - self._last_attempt_started_at)
            if remaining > 0:
                self.sleep(remaining)
                now = self.clock()
        self._last_attempt_started_at = now


def _default_fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read()


def _normalize_requested_id(paper_id: str) -> str:
    normalized = paper_id.strip()
    if not ARXIV_ID_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"arXiv ID must include a version for reproducibility (example 2608.20316v1): {paper_id}"
        )
    return normalized


def _parse_arxiv_entry(xml_bytes: bytes, requested_id: str, source_path: str) -> PaperMetadata:
    """Convert one arXiv Atom response into the local paper contract."""

    namespaces = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as error:
        raise ValueError(f"arXiv returned invalid XML: {error}") from error
    entries = root.findall("atom:entry", namespaces)
    if len(entries) != 1:
        raise ValueError(f"expected one arXiv entry, received {len(entries)}")
    entry = entries[0]

    entry_url = entry.findtext("atom:id", default="", namespaces=namespaces).strip()
    entry_path = unquote(urlsplit(entry_url).path)
    abs_marker = "/abs/"
    if abs_marker not in entry_path:
        raise ValueError("arXiv entry ID must contain an /abs/ path")
    entry_id = entry_path.split(abs_marker, maxsplit=1)[1].strip("/")
    if not entry_id or not ARXIV_ID_PATTERN.fullmatch(entry_id):
        raise ValueError(f"arXiv entry has a missing or malformed versioned ID: {entry_id or '<missing>'}")
    if entry_id.lower() != requested_id.lower():
        raise ValueError(f"arXiv returned {entry_id or 'an entry without an ID'} for {requested_id}")
    version_match = re.search(r"(v\d+)$", entry_id, flags=re.IGNORECASE)
    if version_match is None:
        raise ValueError(f"arXiv entry lacks a version suffix: {entry_id}")

    title = " ".join(entry.findtext("atom:title", default="", namespaces=namespaces).split())
    published_timestamp = entry.findtext("atom:published", default="", namespaces=namespaces)
    authors = [
        " ".join(author.findtext("atom:name", default="", namespaces=namespaces).split())
        for author in entry.findall("atom:author", namespaces)
    ]
    pdf_url = next(
        (
            link.get("href", "")
            for link in entry.findall("atom:link", namespaces)
            if link.get("type") == "application/pdf" or link.get("title") == "pdf"
        ),
        f"https://arxiv.org/pdf/{entry_id}",
    )
    return PaperMetadata.from_dict(
        {
            "paper_id": entry_id,
            "paper_version": version_match.group(1).lower(),
            "title": title,
            "authors": authors,
            "published": published_timestamp[:10],
            "pdf_url": pdf_url.replace("http://", "https://", 1),
            "source_path": source_path,
        }
    )


def collect_arxiv_papers(
    requested_ids: list[str],
    config: PipelineConfig,
    download_pdfs: bool = False,
    fetch: Callable[[str], bytes] = _default_fetch,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> IngestionReport:
    """Collect explicitly selected arXiv records and optionally their PDFs.

    Existing manifest entries and non-empty PDF files are left untouched. Each
    failed metadata or PDF request is reported against its paper ID; successful
    metadata remains reproducibly captured even if an optional download fails.
    """

    normalized_ids = [_normalize_requested_id(paper_id) for paper_id in requested_ids]
    if len(set(normalized_ids)) != len(normalized_ids):
        raise ValueError("requested arXiv IDs must not contain duplicates")

    manifest_path = config.resolve(config.manifest_path)
    existing_papers = load_manifest(manifest_path) if manifest_path.exists() else []
    papers_by_id = {paper.paper_id: paper for paper in existing_papers}
    report = IngestionReport(requested_papers=len(normalized_ids))
    pacer = ArxivRequestPacer(clock=clock, sleep=sleep)

    for paper_id in normalized_ids:
        download_relative_path = config.downloaded_pdf_directory / f"{paper_id}.pdf"
        if paper_id in papers_by_id:
            paper = papers_by_id[paper_id]
            report.existing_papers.append(paper_id)
        else:
            query_url = f"{ARXIV_API_URL}?{urlencode({'id_list': paper_id, 'max_results': 1})}"
            try:
                pacer.wait_for_next_attempt()
                paper = _parse_arxiv_entry(fetch(query_url), paper_id, download_relative_path.as_posix())
            except Exception as error:  # Network and response failures are per-paper outcomes.
                report.failures[paper_id] = f"metadata: {error}"
                continue
            papers_by_id[paper_id] = paper
            report.added_papers.append(paper_id)

        if download_pdfs:
            pdf_path = config.resolve(Path(paper.source_path))
            if pdf_path.is_file() and pdf_path.stat().st_size > 0:
                report.skipped_downloads.append(paper_id)
                continue
            try:
                pdf_bytes = fetch(paper.pdf_url)
                if not pdf_bytes.startswith(b"%PDF-"):
                    raise ValueError("response did not begin with a PDF header")
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                pdf_path.write_bytes(pdf_bytes)
                report.downloaded_pdfs.append(paper_id)
            except Exception as error:  # Report a partial failure without losing metadata.
                report.failures[paper_id] = f"pdf: {error}"

    save_manifest(manifest_path, list(papers_by_id.values()))
    report.manifest_papers = len(papers_by_id)
    successful_requests = len(report.added_papers) + len(report.existing_papers)
    if not report.failures:
        report.outcome = SUCCESS
    elif successful_requests:
        report.outcome = PARTIAL_FAILURE
    else:
        report.outcome = FAILURE
    return report
