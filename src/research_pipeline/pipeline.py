"""Local preparation runners using merged ingestion/extraction and safe generations."""

from __future__ import annotations

from dataclasses import replace
from importlib.metadata import version
from pathlib import Path
import platform
import tempfile

from research_pipeline.chunking import ChunkingConfig, CitationChunk, build_chunks, profile_record, sha256_bytes
from research_pipeline.config import PipelineConfig
from research_pipeline.datasets import FAILURE_CATEGORIES, publish_dataset, quality_facts, write_run_manifest
from research_pipeline.extraction import extract_manifest_pages
from research_pipeline.ingestion import build_paper_catalog, load_manifest
from research_pipeline.models import ExtractedPage, PaperMetadata
from research_pipeline.storage import read_jsonl, write_json, write_jsonl


def _file_hash(path: Path) -> str | None:
    return sha256_bytes(path.read_bytes()) if path.is_file() else None


def _check_paths(config: PipelineConfig, papers, run_root: Path, pointer_path: Path,
                 extra_inputs: tuple[Path, ...]) -> None:
    inputs = [config.resolve(config.manifest_path), config.resolve(config.paper_catalog_path),
              config.resolve(config.extracted_pages_path), *extra_inputs,
              *(config.resolve(Path(paper.source_path)) for paper in papers)]
    if run_root.is_symlink() or pointer_path.is_symlink():
        raise ValueError("run root and active pointer must not be symlinks")
    root, pointer = run_root.resolve(), pointer_path.resolve()
    if pointer == root or pointer.is_relative_to(root):
        raise ValueError("active pointer must be outside the immutable run root")
    for path in inputs:
        resolved = path.resolve()
        if resolved.is_relative_to(root) or resolved == pointer or (
                path.is_file() and pointer_path.is_file() and path.samefile(pointer_path)):
            raise ValueError("publication paths alias or contain a source input")


def _snapshot(paths: list[Path]) -> dict[Path, str | None]:
    return {path: _file_hash(path) for path in paths}


def _verify_sources(before: dict[Path, str | None]) -> None:
    if any(_file_hash(path) != digest for path, digest in before.items()):
        raise ValueError("source input changed during processing; dataset was not published")


def _tokenizer_sources(tokenizer) -> dict[Path, str | None]:
    if tokenizer is None:
        return {}
    path = Path(tokenizer.source_path)
    digest = tokenizer.provenance()["asset_sha256"]
    if _file_hash(path) != digest:
        raise ValueError("local tokenizer source changed since loading")
    return {path: digest}


def _finish(staging: Path, papers, pages, chunks, config: ChunkingConfig, tokenizer,
            provenance: dict, run_root: Path, pointer_path: Path, allow_partial: bool,
            snapshots: dict[Path, str | None], source_failures: dict) -> dict:
    """Materialize/read back a candidate, then select it only when permitted."""
    included = sorted({page.paper_id for page in pages if page.text.strip()})
    requested = sorted(paper.paper_id for paper in papers)
    outcome = "failure" if not chunks else (
        "success" if included == requested else "partial_failure")
    write_jsonl(staging / "papers.jsonl", (paper.to_dict() for paper in sorted(
        papers, key=lambda paper: paper.paper_id)))
    write_jsonl(staging / "pages.jsonl", (page.to_dict() for page in sorted(
        pages, key=lambda page: (page.paper_id, page.page_number))))
    write_jsonl(staging / "chunks.jsonl", (chunk.to_dict() for chunk in chunks))
    roundtrip = read_jsonl(staging / "chunks.jsonl", CitationChunk.from_dict) == chunks if chunks else None
    if chunks and roundtrip is not True:
        raise ValueError("chunk storage round trip changed citations or text")
    report = {**quality_facts(papers, pages, chunks, config.profile), "source_failures": source_failures}
    write_json(staging / "quality_report.json", report)
    _verify_sources(snapshots)
    published = False
    generation = None
    if outcome == "success" or (outcome == "partial_failure" and allow_partial):
        write_run_manifest(staging, profile_record(config, tokenizer), provenance, outcome)
        selected = publish_dataset(staging, run_root, pointer_path)
        published = True
        generation = selected.directory.name
    return {**report, "artifacts_published": published, "generation": generation}


def _locations(config, run_root, pointer_path):
    root = config.resolve(Path("data/processed/runs") if run_root is None else Path(run_root))
    pointer = config.resolve(Path("data/processed/active_run.json") if pointer_path is None else Path(pointer_path))
    return root, pointer


def run_pipeline(config: PipelineConfig, chunking: ChunkingConfig = ChunkingConfig(),
                 run_root: Path | None = None, pointer_path: Path | None = None,
                 allow_partial: bool = False, tokenizer=None) -> dict:
    """Run ingestion, extraction and chunking offline, preserving prior active data.

    All stage writes use a temporary directory. The legacy catalog/pages outputs
    remain untouched. Malformed inputs, changed sources, and filesystem failures
    raise; a caller CLI reports failure/code 3. Usable partial results require an
    explicit flag and remain partial/code 2 even when published.
    """
    profile_record(chunking, tokenizer)
    manifest_path = config.resolve(config.manifest_path)
    manifest_hash = _file_hash(manifest_path)
    papers = load_manifest(manifest_path, config.repository_root)
    run_root, pointer_path = _locations(config, run_root, pointer_path)
    tokenizer_sources = _tokenizer_sources(tokenizer)
    _check_paths(config, papers, run_root, pointer_path, tuple(tokenizer_sources))
    source_paths = {paper.paper_id: config.resolve(Path(paper.source_path)) for paper in papers}
    snapshots = {manifest_path: manifest_hash, **_snapshot(list(source_paths.values())), **tokenizer_sources}
    hashes = {"manifest": manifest_hash, **{
        "pdf:" + paper_id: snapshots[path] for paper_id, path in source_paths.items()
        if snapshots[path] is not None}}
    provenance = {"input_mode": "pdf_pipeline", "source_hashes": hashes,
                  "dependencies": {"python": platform.python_version(),
                                   "pypdf": version("pypdf"), "fonttools": version("fonttools")}}
    run_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".staging-", dir=run_root) as directory:
        staging = Path(directory)
        staged_config = replace(config, paper_catalog_path=staging / "papers.jsonl",
                                extracted_pages_path=staging / "pages.jsonl")
        build_paper_catalog(staged_config)
        extraction_report = extract_manifest_pages(staged_config)
        pages = read_jsonl(staging / "pages.jsonl", ExtractedPage.from_dict)
        chunks = build_chunks(pages, papers, chunking, tokenizer)
        failures = {"missing_pdfs": sorted(extraction_report.missing_pdfs),
                    "parsing_failures": sorted(extraction_report.parsing_failures),
                    "papers_without_usable_text": sorted(extraction_report.papers_without_usable_text),
                    "missing_page_papers": []}
        return _finish(staging, papers, pages, chunks, chunking, tokenizer, provenance,
                       run_root, pointer_path, allow_partial, snapshots, failures)


def run_chunking(config: PipelineConfig, chunking: ChunkingConfig = ChunkingConfig(),
                 run_root: Path | None = None, pointer_path: Path | None = None,
                 allow_partial: bool = False, tokenizer=None, catalog_path: Path | None = None) -> dict:
    """Publish passages from existing page JSONL without parsing or changing PDFs.

    The manifest supplies catalog metadata unless an explicit catalog is given;
    an explicit catalog must agree with it. Missing paper pages are partial, and
    malformed/gapped/duplicate pages are errors rather than publishable omissions.
    """
    profile_record(chunking, tokenizer)
    manifest_path = config.resolve(config.manifest_path)
    manifest_hash = _file_hash(manifest_path)
    papers = load_manifest(manifest_path, config.repository_root)
    pages_path = config.resolve(config.extracted_pages_path)
    catalog_path = config.resolve(Path(catalog_path)) if catalog_path is not None else None
    extra = (pages_path,) if catalog_path is None else (pages_path, catalog_path)
    run_root, pointer_path = _locations(config, run_root, pointer_path)
    tokenizer_sources = _tokenizer_sources(tokenizer)
    _check_paths(config, papers, run_root, pointer_path, (*extra, *tokenizer_sources))
    snapshots = {manifest_path: manifest_hash, **_snapshot(list(extra)), **tokenizer_sources}
    if catalog_path is not None:
        catalog = read_jsonl(catalog_path, PaperMetadata.from_dict)
        if sorted(catalog, key=lambda paper: paper.paper_id) != sorted(papers, key=lambda paper: paper.paper_id):
            raise ValueError("explicit catalog differs from manifest")
    pages = read_jsonl(pages_path, ExtractedPage.from_dict)
    chunks = build_chunks(pages, papers, chunking, tokenizer)
    hashes = {"manifest": manifest_hash, "pages": snapshots[pages_path]}
    if catalog_path is not None:
        hashes["catalog"] = snapshots[catalog_path]
    provenance = {"input_mode": "existing_pages", "source_hashes": hashes,
                  "dependencies": {"python": platform.python_version()}}
    run_root.mkdir(parents=True, exist_ok=True)
    represented = {page.paper_id for page in pages}
    usable = {page.paper_id for page in pages if page.text.strip()}
    failures = {field: [] for field in FAILURE_CATEGORIES}
    failures["missing_page_papers"] = sorted({paper.paper_id for paper in papers} - represented)
    failures["papers_without_usable_text"] = sorted(represented - usable)
    with tempfile.TemporaryDirectory(prefix=".staging-", dir=run_root) as directory:
        return _finish(Path(directory), papers, pages, chunks, chunking, tokenizer,
                       provenance, run_root, pointer_path, allow_partial, snapshots, failures)
