"""Deterministic page-local passages with reconstructable Unicode source spans."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any

from research_pipeline.models import ExtractedPage, PaperMetadata


ALGORITHM_VERSION = "page-spans-v1"
CITATION_FIELDS = ("paper_id", "paper_version", "title", "authors", "published", "pdf_url")


def sha256_bytes(value: bytes) -> str:
    """Hash exact bytes, not a platform-dependent string representation."""
    return hashlib.sha256(value).hexdigest()


def canonical_hash(value: object) -> str:
    """Hash JSON content with stable Unicode, key ordering and separators."""
    return sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":"), allow_nan=False).encode("utf-8"))


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _hash(value: Any, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError(f"{name} must be a lowercase SHA-256 hash")
    return value


@dataclass(frozen=True)
class ChunkingConfig:
    """Explicit budgets; characters are code points, token budgets are actual counts."""

    profile: str = "boundary_characters"
    size: int = 1800
    overlap: int = 200
    token_budget: int = 200
    token_overlap: int = 40
    max_input_tokens: int = 256

    def __post_init__(self) -> None:
        if self.profile not in ("boundary_characters", "fixed_characters", "tokenizer"):
            raise ValueError("unsupported chunking profile")
        for name in ("size", "token_budget", "max_input_tokens"):
            _integer(getattr(self, name), name, 1)
        for name in ("overlap", "token_overlap"):
            _integer(getattr(self, name), name)
        if self.overlap >= self.size or self.token_overlap >= self.token_budget:
            raise ValueError("overlap must be smaller than its corresponding budget")
        if self.token_budget > self.max_input_tokens:
            raise ValueError("content token budget exceeds complete input budget")

    def to_dict(self) -> dict[str, Any]:
        return {"algorithm_version": ALGORITHM_VERSION, **asdict(self)}


@dataclass(frozen=True)
class CitationChunk(ExtractedPage):
    """A nonempty exact page substring; offsets are zero-based, half-open code points."""

    schema_version: int
    chunk_id: str
    start_character: int
    end_character: int
    page_text_sha256: str
    chunking_profile_sha256: str
    content_token_count: int | None
    input_token_count: int | None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CitationChunk:
        """Validate a stored chunk's shape; source linkage is checked separately.

        Raises ValueError for unknown schemas, invalid citations, offsets, hashes,
        empty text, inconsistent token counts, or non-object JSON records.
        """
        if not isinstance(value, dict):
            raise ValueError("chunk must be a JSON object")
        if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
            raise ValueError("unsupported chunk schema_version")
        required = {"chunk_id", "start_character", "end_character", "page_text_sha256",
                    "chunking_profile_sha256", "content_token_count", "input_token_count"}
        if required - value.keys():
            raise ValueError("missing required chunk fields")
        source = ExtractedPage.from_dict(value)
        if not source.text:
            raise ValueError("chunk text must not be empty")
        start = _integer(value.get("start_character"), "start_character")
        end = _integer(value.get("end_character"), "end_character", start + 1)
        if end - start != len(source.text):
            raise ValueError("offset length differs from chunk text")
        chunk_id = value.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id:
            raise ValueError("chunk_id is required")
        counts = [value.get("content_token_count"), value.get("input_token_count")]
        if (counts[0] is None) != (counts[1] is None):
            raise ValueError("token counts must both be known or null")
        for count in counts:
            if count is not None:
                _integer(count, "token count")
        if counts[0] is not None and counts[0] > counts[1]:
            raise ValueError("content count exceeds complete input count")
        fields = source.to_dict()
        fields["authors"] = source.authors
        return cls(**fields, schema_version=1, chunk_id=chunk_id,
                   start_character=start, end_character=end,
                   page_text_sha256=_hash(value.get("page_text_sha256"), "page_text_sha256"),
                   chunking_profile_sha256=_hash(value.get("chunking_profile_sha256"),
                                                "chunking_profile_sha256"),
                   content_token_count=counts[0], input_token_count=counts[1])


def profile_record(config: ChunkingConfig, tokenizer=None) -> dict[str, Any]:
    """Effective settings and local tokenizer provenance, with no machine paths."""
    if config.profile == "tokenizer" and tokenizer is None:
        raise ValueError("tokenizer profile requires an explicit local tokenizer")
    return {**config.to_dict(), "tokenizer": tokenizer.provenance()
            if config.profile == "tokenizer" else None}


def chunk_identity(record: dict[str, Any]) -> str:
    """Content-sensitive ID including all citation fields and original page identity."""
    fields = (*CITATION_FIELDS, "page_number", "start_character", "end_character",
              "page_text_sha256", "chunking_profile_sha256", "text")
    digest = canonical_hash({name: record[name] for name in fields})
    return f"{record['paper_id']}:p{record['page_number']:04d}:{digest}"


def _preferred_end(text: str, start: int, hard_end: int, minimum: int) -> int:
    if hard_end == len(text):
        return hard_end
    section = text[start:hard_end]
    for pattern in (r"\n\s*\n", r"[.!?](?:[\"')\]]*)\s+", r"\s+"):
        positions = [start + match.end() for match in re.finditer(pattern, section)
                     if start + match.end() >= minimum]
        if pattern == r"\s+" and text[hard_end].isspace() and hard_end >= minimum:
            positions.append(hard_end)
        if positions:
            return positions[-1]
    return hard_end


def chunk_page(page: ExtractedPage, config: ChunkingConfig, tokenizer=None) -> list[CitationChunk]:
    """Split a validated page without altering source text or crossing a page.

    Character overlap is exact. Token overlap uses source offsets of the last
    N tokens, with progress clamping; retokenization may change its actual count.
    All-whitespace pages are skipped; rare whitespace-only windows are retained.
    Raises ValueError when a profile cannot satisfy its budget or make progress.
    """
    page = ExtractedPage.from_dict(page.to_dict())
    settings_hash = canonical_hash(profile_record(config, tokenizer))
    if not page.text.strip():
        return []
    source_hash = sha256_bytes(page.text.encode("utf-8"))
    chunks = []
    start = 0
    while start < len(page.text):
        if config.profile == "tokenizer":
            # Implemented by the optional adapter, never approximated from characters.
            end, next_start, counts = tokenizer.window(page.text, start, config)
        else:
            end = min(start + config.size, len(page.text))
            if config.profile == "boundary_characters":
                end = _preferred_end(page.text, start, end, start + config.overlap + 1)
            next_start = end - config.overlap
            counts = (None, None)
        if not start < end <= len(page.text) or (end < len(page.text) and next_start <= start):
            raise ValueError("chunking failed to advance within the source page")
        record = {**page.to_dict(), "text": page.text[start:end], "schema_version": 1,
                  "start_character": start, "end_character": end,
                  "page_text_sha256": source_hash, "chunking_profile_sha256": settings_hash,
                  "content_token_count": counts[0], "input_token_count": counts[1]}
        record["chunk_id"] = chunk_identity(record)
        chunks.append(CitationChunk.from_dict(record))
        if end == len(page.text):
            break
        start = next_start
    return chunks


def validate_pages(pages: list[ExtractedPage], papers: list[PaperMetadata]) -> list[ExtractedPage]:
    """Reject duplicate/gapped pages and citation conflicts before sorting them."""
    paper_map = {paper.paper_id: PaperMetadata.from_dict(paper.to_dict()) for paper in papers}
    if len(paper_map) != len(papers):
        raise ValueError("duplicate paper identities")
    seen = set()
    positions: dict[str, list[int]] = {}
    validated = []
    for page in pages:
        page = ExtractedPage.from_dict(page.to_dict())
        key = (page.paper_id, page.page_number)
        if key in seen:
            raise ValueError("duplicate paper/page record")
        seen.add(key)
        paper = paper_map.get(page.paper_id)
        if paper is None or any(page.to_dict()[field] != paper.to_dict()[field]
                                for field in CITATION_FIELDS):
            raise ValueError("page citation metadata does not match its manifest paper")
        positions.setdefault(page.paper_id, []).append(page.page_number)
        validated.append(page)
    for numbers in positions.values():
        if sorted(numbers) != list(range(1, len(numbers) + 1)):
            raise ValueError("paper page numbers must be contiguous from 1")
    return sorted(validated, key=lambda page: (page.paper_id, page.page_number))


def validate_chunks(chunks: list[CitationChunk], pages: list[ExtractedPage],
                    papers: list[PaperMetadata]) -> None:
    """Prove IDs, citations, exact slicing, unique spans and complete page coverage."""
    pages = validate_pages(pages, papers)
    page_map = {(page.paper_id, page.page_number): page for page in pages}
    grouped: dict[tuple[str, int], list[CitationChunk]] = {}
    seen_ids = set()
    for chunk in chunks:
        record = chunk.to_dict()
        CitationChunk.from_dict(record)
        key = (chunk.paper_id, chunk.page_number)
        page = page_map.get(key)
        if page is None or not page.text.strip():
            raise ValueError("chunk references a missing or blank source page")
        if any(record[field] != page.to_dict()[field] for field in CITATION_FIELDS):
            raise ValueError("chunk citation metadata differs from its page")
        if chunk.end_character > len(page.text) or chunk.text != page.text[
                chunk.start_character:chunk.end_character]:
            raise ValueError("chunk cannot be reconstructed from its cited page")
        if chunk.page_text_sha256 != sha256_bytes(page.text.encode("utf-8")):
            raise ValueError("chunk page text hash differs from its source")
        if chunk.chunk_id != chunk_identity(record) or chunk.chunk_id in seen_ids:
            raise ValueError("invalid or duplicate chunk_id")
        seen_ids.add(chunk.chunk_id)
        grouped.setdefault(key, []).append(chunk)
    for key, page in page_map.items():
        if not page.text.strip():
            continue
        reached = 0
        last_start = -1
        for chunk in sorted(grouped.get(key, []), key=lambda chunk: chunk.start_character):
            if chunk.start_character > reached or chunk.start_character <= last_start:
                raise ValueError("chunk coverage has a gap or duplicate source span")
            reached = max(reached, chunk.end_character)
            last_start = chunk.start_character
        if reached != len(page.text):
            raise ValueError("chunk coverage does not include the complete page")


def build_chunks(pages: list[ExtractedPage], papers: list[PaperMetadata],
                 config: ChunkingConfig, tokenizer=None) -> list[CitationChunk]:
    """Build and verify sorted page-local chunks from existing ingestion contracts."""
    pages = validate_pages(pages, papers)
    chunks = [chunk for page in pages for chunk in chunk_page(page, config, tokenizer)]
    validate_chunks(chunks, pages, papers)
    return chunks
