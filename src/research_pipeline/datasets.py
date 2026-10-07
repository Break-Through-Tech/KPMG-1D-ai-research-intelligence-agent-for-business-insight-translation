"""Complete generation publication and source-validating, model-neutral loaders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research_pipeline.chunking import (
    ALGORITHM_VERSION, ChunkingConfig, CitationChunk, _hash, _integer,
    build_chunks, canonical_hash, sha256_bytes, validate_chunks,
)
from research_pipeline.models import ARXIV_ID_PATTERN, ExtractedPage, PaperMetadata
from research_pipeline.storage import read_json, read_jsonl, write_json


ARTIFACTS = ("papers.jsonl", "pages.jsonl", "chunks.jsonl", "quality_report.json")
FAILURE_CATEGORIES = ("missing_pdfs", "parsing_failures", "papers_without_usable_text", "missing_page_papers")


def quality_facts(papers, pages, chunks, profile: str) -> dict:
    """Derive report facts from records, never trust a stored summary's counts."""
    included = sorted({page.paper_id for page in pages if page.text.strip()})
    requested = sorted(paper.paper_id for paper in papers)
    return {
        "outcome": "failure" if not chunks else ("success" if included == requested else "partial_failure"),
        "pages_loaded": len(pages), "chunks_written": len(chunks),
        "storage_round_trip_valid": True if chunks else None,
        "unique_chunk_ids": len({chunk.chunk_id for chunk in chunks}),
        "requested_paper_ids": requested, "included_paper_ids": included,
        "excluded_paper_ids": sorted(set(requested) - set(included)),
        "blank_pages": [{"paper_id": page.paper_id, "page_number": page.page_number}
                        for page in sorted(pages, key=lambda page: (page.paper_id, page.page_number))
                        if not page.text.strip()],
        "whitespace_chunk_count": sum(not chunk.text.strip() for chunk in chunks),
        "maximum_chunk_characters": max((len(chunk.text) for chunk in chunks), default=0),
        "chunk_counts_by_paper": {paper_id: sum(chunk.paper_id == paper_id for chunk in chunks)
                                  for paper_id in requested},
        "tokenizer_validation": "local_asset_counts_verified; model_identity_declared_not_authenticated"
        if profile == "tokenizer" else "not_requested",
    }


@dataclass(frozen=True)
class Dataset:
    """A verified generation; all records originate from the same selected run."""

    directory: Path
    papers: list[PaperMetadata]
    pages: list[ExtractedPage]
    chunks: list[CitationChunk]
    manifest: dict[str, Any]


def _object(value: Any, name: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _ids(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not
            ARXIV_ID_PATTERN.fullmatch(item) for item in value):
        raise ValueError(f"{name} must contain canonical versioned paper IDs")
    if value != sorted(set(value)):
        raise ValueError(f"{name} must be sorted and unique")
    return value


def _artifact_path(directory: Path, name: str) -> Path:
    path = directory / name
    if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("dataset artifact escapes its generation")
    if not path.is_file():
        raise ValueError(f"missing dataset artifact: {name}")
    return path


def _read_records(directory: Path):
    papers = read_jsonl(_artifact_path(directory, "papers.jsonl"), PaperMetadata.from_dict)
    pages = read_jsonl(_artifact_path(directory, "pages.jsonl"), ExtractedPage.from_dict)
    chunks = read_jsonl(_artifact_path(directory, "chunks.jsonl"), CitationChunk.from_dict)
    report = _object(read_json(_artifact_path(directory, "quality_report.json")), "quality report")
    return papers, pages, chunks, report


def write_run_manifest(directory: Path, chunking: dict, provenance: dict, outcome: str) -> dict:
    """Record exact candidate artifact hashes, counts, effective settings and coverage.

    The manifest does not hash itself. Its own hash names the immutable generation
    and is recorded in the active pointer, avoiding recursive hash dependencies.
    The caller must run full dataset validation before publication.
    """
    papers, pages, chunks, report = _read_records(directory)
    included = sorted({page.paper_id for page in pages if page.text.strip()})
    requested = sorted(paper.paper_id for paper in papers)
    counts = dict(zip(ARTIFACTS, (len(papers), len(pages), len(chunks), 1)))
    manifest = {
        "schema_version": 1, "algorithm_version": ALGORITHM_VERSION,
        "chunking": chunking, "provenance": provenance, "outcome": outcome,
        "requested_paper_ids": requested, "included_paper_ids": included,
        "excluded_paper_ids": sorted(set(requested) - set(included)),
        "page_counts": {paper_id: sum(page.paper_id == paper_id for page in pages)
                        for paper_id in requested},
        "artifacts": {name: {"sha256": sha256_bytes(_artifact_path(directory, name).read_bytes()),
                              "record_count": counts[name]} for name in ARTIFACTS},
    }
    write_json(directory / "run_manifest.json", manifest)
    return manifest


def _validate_profile(record: Any) -> ChunkingConfig:
    record = _object(record, "chunking settings")
    if record.get("algorithm_version") != ALGORITHM_VERSION:
        raise ValueError("unsupported chunking algorithm_version")
    fields = ("profile", "size", "overlap", "token_budget", "token_overlap", "max_input_tokens")
    if set(record) != {*fields, "algorithm_version", "tokenizer"}:
        raise ValueError("incomplete or unsupported chunking configuration")
    config = ChunkingConfig(**{name: record[name] for name in fields})
    tokenizer = record["tokenizer"]
    if config.profile == "tokenizer":
        tokenizer = _object(tokenizer, "tokenizer provenance")
        for field in ("model_id", "revision", "library", "library_version", "input_template"):
            if not isinstance(tokenizer.get(field), str) or not tokenizer[field].strip():
                raise ValueError("incomplete tokenizer provenance")
        _hash(tokenizer.get("asset_sha256"), "tokenizer asset hash")
        if tokenizer["input_template"] != "chunk_text_only" or tokenizer["library"] != "tokenizers":
            raise ValueError("unsupported tokenizer input template or library")
    elif tokenizer is not None:
        raise ValueError("character profile must not declare a tokenizer")
    return config


def load_generation(directory: Path, manifest_hash: str | None = None) -> Dataset:
    """Reject incomplete, corrupted or semantically inconsistent published data.

    Checks schemas, hashes/counts, coverage declarations, metadata, source slices,
    IDs and budgets. Character profiles are regenerated exactly. Token counts
    are checked against stored budgets; independently recounting them requires
    the original tokenizer asset, not a network request from this loader.
    """
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("generation must be a real directory")
    manifest_path = _artifact_path(directory, "run_manifest.json")
    if manifest_hash is not None and sha256_bytes(manifest_path.read_bytes()) != _hash(
            manifest_hash, "run manifest hash"):
        raise ValueError("run manifest hash mismatch")
    manifest = _object(read_json(manifest_path), "run manifest")
    required = {"schema_version", "algorithm_version", "chunking", "provenance", "outcome",
                "requested_paper_ids", "included_paper_ids", "excluded_paper_ids",
                "page_counts", "artifacts"}
    if set(manifest) != required or type(manifest.get("schema_version")) is not int or manifest[
            "schema_version"] != 1 or manifest["algorithm_version"] != ALGORITHM_VERSION:
        raise ValueError("unsupported or incomplete run manifest")
    config = _validate_profile(manifest["chunking"])
    provenance = _object(manifest["provenance"], "provenance")
    if provenance.get("input_mode") not in ("existing_pages", "pdf_pipeline"):
        raise ValueError("unsupported or missing input_mode")
    dependencies = _object(provenance.get("dependencies"), "dependency provenance")
    if not dependencies or any(not isinstance(v, str) or not v for v in dependencies.values()):
        raise ValueError("incomplete dependency provenance")
    required_dependencies = {"python"} if provenance["input_mode"] == "existing_pages" else {
        "python", "pypdf", "fonttools"}
    if not required_dependencies.issubset(dependencies):
        raise ValueError("mode-specific dependency provenance missing")
    source_hashes = _object(provenance.get("source_hashes"), "source hashes")
    if "manifest" not in source_hashes:
        raise ValueError("source manifest hash missing")
    for digest in source_hashes.values():
        _hash(digest, "source hash")
    artifacts = _object(manifest["artifacts"], "artifacts")
    if set(artifacts) != set(ARTIFACTS):
        raise ValueError("incomplete publication artifact manifest")
    for name in ARTIFACTS:
        details = _object(artifacts[name], "artifact details")
        if set(details) != {"sha256", "record_count"}:
            raise ValueError("incomplete artifact details")
        _integer(details["record_count"], "record_count")
        if sha256_bytes(_artifact_path(directory, name).read_bytes()) != _hash(details["sha256"], name):
            raise ValueError(f"artifact hash mismatch: {name}")
    papers, pages, chunks, report = _read_records(directory)
    required_sources = ({"pages"} if provenance["input_mode"] == "existing_pages" else
                        {"pdf:" + page.paper_id for page in pages})
    if not required_sources.issubset(source_hashes):
        raise ValueError("mode-specific source hash missing")
    counts = dict(zip(ARTIFACTS, (len(papers), len(pages), len(chunks), 1)))
    if any(artifacts[name]["record_count"] != count for name, count in counts.items()):
        raise ValueError("artifact record count mismatch")
    validate_chunks(chunks, pages, papers)
    requested = _ids(manifest["requested_paper_ids"], "requested_paper_ids")
    included = _ids(manifest["included_paper_ids"], "included_paper_ids")
    excluded = _ids(manifest["excluded_paper_ids"], "excluded_paper_ids")
    if requested != sorted(paper.paper_id for paper in papers) or included != sorted({
            page.paper_id for page in pages if page.text.strip()}) or excluded != sorted(
            set(requested) - set(included)):
        raise ValueError("manifest coverage contradicts source records")
    expected_outcome = "success" if included == requested else "partial_failure"
    if not included or not chunks or manifest["outcome"] != expected_outcome:
        raise ValueError("published dataset has no usable corpus or incorrect outcome")
    page_counts = _object(manifest["page_counts"], "page counts")
    if set(page_counts) != set(requested) or any(type(value) is not int for value in page_counts.values()):
        raise ValueError("invalid declared page counts")
    if page_counts != {paper_id: sum(page.paper_id == paper_id for page in pages) for paper_id in requested}:
        raise ValueError("source page counts differ from manifest")
    facts = quality_facts(papers, pages, chunks, config.profile)
    if set(report) != {*facts, "source_failures"} or any(
            canonical_hash(report[field]) != canonical_hash(value) for field, value in facts.items()):
        raise ValueError("quality report contradicts validated dataset or omits required facts")
    failures = _object(report["source_failures"], "source failures")
    if set(failures) != set(FAILURE_CATEGORIES):
        raise ValueError("incomplete source failure classifications")
    classified = [paper_id for field in FAILURE_CATEGORIES for paper_id in _ids(failures[field], field)]
    if sorted(classified) != excluded:
        raise ValueError("failure classifications contradict corpus exclusions")
    if provenance["input_mode"] == "pdf_pipeline":
        if any("pdf:" + paper_id not in source_hashes for category in (
                "parsing_failures", "papers_without_usable_text") for paper_id in failures[category]):
            raise ValueError("failed/no-text PDF source hash missing")
        if failures["missing_page_papers"] or any(source_hashes.get("pdf:" + paper_id) not in (
                None, sha256_bytes(b"")) for paper_id in failures["missing_pdfs"]):
            raise ValueError("PDF failure classifications contradict provenance")
    elif failures["missing_pdfs"] or failures["parsing_failures"] or failures["missing_page_papers"] != sorted(
            set(requested) - {page.paper_id for page in pages}):
        raise ValueError("existing-page failure classifications contradict page records")
    profile_hash = canonical_hash(manifest["chunking"])
    if any(chunk.chunking_profile_sha256 != profile_hash for chunk in chunks):
        raise ValueError("chunk profile hash differs from effective run settings")
    if config.profile != "tokenizer":
        if chunks != build_chunks(pages, papers, config):
            raise ValueError("character chunks do not match the declared algorithm")
    else:
        if any(chunk.content_token_count is None or chunk.input_token_count is None or
               chunk.content_token_count > config.token_budget or chunk.input_token_count >
               config.max_input_tokens for chunk in chunks):
            raise ValueError("token chunk counts violate declared budgets")
    return Dataset(directory, papers, pages, chunks, manifest)


def publish_dataset(staging: Path, run_root: Path, pointer_path: Path) -> Dataset:
    """Select a complete immutable generation with one atomic pointer replacement.

    Validation/directory/pointer failures leave the previous selection untouched.
    A completed unselected directory may remain after interruption. This is not
    a power-loss durability or concurrent-writer protocol.
    """
    staging, run_root, pointer_path = Path(staging), Path(run_root), Path(pointer_path)
    load_generation(staging)
    digest = sha256_bytes((staging / "run_manifest.json").read_bytes())
    if run_root.is_symlink():
        raise ValueError("run root must not be a symlink")
    run_root.mkdir(parents=True, exist_ok=True)
    destination = run_root / digest
    if destination.exists() or destination.is_symlink():
        load_generation(destination, digest)
    else:
        staging.rename(destination)
    selected = load_generation(destination, digest)
    write_json(pointer_path, {"schema_version": 1, "generation": digest,
                              "run_manifest_sha256": digest})
    return selected


def load_active_dataset(run_root: Path, pointer_path: Path) -> Dataset:
    """Resolve one active generation and verify all stored hashes and source links."""
    run_root, pointer_path = Path(run_root), Path(pointer_path)
    if run_root.is_symlink() or pointer_path.is_symlink():
        raise ValueError("run root and active pointer must not be symlinks")
    pointer = _object(read_json(pointer_path), "active pointer")
    if set(pointer) != {"schema_version", "generation", "run_manifest_sha256"} or type(
            pointer.get("schema_version")) is not int or pointer["schema_version"] != 1:
        raise ValueError("unsupported or incomplete active pointer")
    generation = _hash(pointer["generation"], "generation")
    digest = _hash(pointer["run_manifest_sha256"], "manifest hash")
    if generation != digest:
        raise ValueError("generation identity differs from manifest hash")
    directory = run_root / generation
    if directory.is_symlink() or not directory.resolve().is_relative_to(run_root.resolve()):
        raise ValueError("generation escapes the configured run root")
    return load_generation(directory, digest)


def load_passages(run_root: Path, pointer_path: Path, paper_ids: list[str] | None = None) -> list[CitationChunk]:
    """Return validated passages, optionally restricted to candidate paper IDs.

    This is a data handoff, not vector search, ranking, or a retrieval integration.
    """
    chunks = load_active_dataset(run_root, pointer_path).chunks
    if paper_ids is None:
        return chunks
    wanted = set(_ids(sorted(paper_ids), "paper filter"))
    return [chunk for chunk in chunks if chunk.paper_id in wanted]
