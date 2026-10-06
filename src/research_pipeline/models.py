"""Validated paper metadata and source-preserving PDF page contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
import re
from typing import Any


ARXIV_ID_PATTERN = re.compile(r"^(?:[a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})v\d+$", re.IGNORECASE)


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True)
class PaperMetadata:
    """A reproducible paper record keyed by its versioned arXiv identifier.

    ``paper_id`` includes the version suffix for compatibility with the existing
    retrieval branch. ``paper_version`` is retained separately for citation and
    validation needs. ``source_path`` is repository-relative.
    """

    paper_id: str
    paper_version: str
    title: str
    authors: tuple[str, ...]
    published: str
    pdf_url: str
    source_path: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> PaperMetadata:
        """Validate and construct metadata from a JSON-compatible mapping."""

        required = {
            "paper_id",
            "paper_version",
            "title",
            "authors",
            "published",
            "pdf_url",
            "source_path",
        }
        missing = sorted(required - value.keys())
        if missing:
            raise ValueError(f"missing paper metadata fields: {', '.join(missing)}")

        paper_id = _required_text(value["paper_id"], "paper_id")
        paper_version = _required_text(value["paper_version"], "paper_version")
        if not ARXIV_ID_PATTERN.fullmatch(paper_id):
            raise ValueError(f"paper_id is not a versioned arXiv ID: {paper_id}")
        if not re.fullmatch(r"v[1-9]\d*", paper_version):
            raise ValueError(f"paper_version is invalid: {paper_version}")
        if not paper_id.lower().endswith(paper_version.lower()):
            raise ValueError("paper_version must match the suffix of paper_id")

        authors_value = value["authors"]
        if not isinstance(authors_value, (list, tuple)) or not authors_value:
            raise ValueError("authors must be a non-empty list")
        authors = tuple(_required_text(author, "author") for author in authors_value)

        published = _required_text(value["published"], "published")
        try:
            date.fromisoformat(published)
        except ValueError as error:
            raise ValueError("published must use ISO date format YYYY-MM-DD") from error

        pdf_url = _required_text(value["pdf_url"], "pdf_url")
        if not pdf_url.startswith(("https://arxiv.org/pdf/", "http://arxiv.org/pdf/")):
            raise ValueError("pdf_url must point to an arXiv PDF")

        source_path = _required_text(value["source_path"], "source_path")
        source_parts = Path(source_path).parts
        if Path(source_path).is_absolute() or ".." in source_parts:
            raise ValueError("source_path must be repository-relative and cannot contain '..'")

        return cls(
            paper_id=paper_id,
            paper_version=paper_version,
            title=_required_text(value["title"], "title"),
            authors=authors,
            published=published,
            pdf_url=pdf_url,
            source_path=source_path,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible record with authors represented as a list."""

        record = asdict(self)
        record["authors"] = list(self.authors)
        return record


@dataclass(frozen=True)
class ExtractedPage:
    """One original PDF page with complete paper citation metadata.

    Page numbers are 1-based physical PDF positions, not printed page labels.
    Blank pages retain their position and have an empty text string.
    """

    paper_id: str
    paper_version: str
    title: str
    authors: tuple[str, ...]
    published: str
    pdf_url: str
    page_number: int
    text: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible page with an ordered author list."""

        record = asdict(self)
        record["authors"] = list(self.authors)
        return record

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ExtractedPage:
        """Validate citation metadata, a positive page number, and string text.

        Raises ValueError for malformed records. Page records intentionally
        omit the local PDF path; citation fields share the paper contract.
        """

        metadata = PaperMetadata.from_dict({**value, "source_path": "not-used.pdf"})
        page_number = value.get("page_number")
        if isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1:
            raise ValueError("page_number must be a positive integer")
        text = value.get("text")
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        return cls(
            paper_id=metadata.paper_id,
            paper_version=metadata.paper_version,
            title=metadata.title,
            authors=metadata.authors,
            published=metadata.published,
            pdf_url=metadata.pdf_url,
            page_number=page_number,
            text=text,
        )
