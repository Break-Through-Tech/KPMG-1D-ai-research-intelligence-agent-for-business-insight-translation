"""Representative offline verification; run with PYTHONPATH=src python -m tests.validate_pr3_corpus."""

from pathlib import Path
import json
import socket
import tempfile
from unittest.mock import patch

from pypdf import PdfReader

from research_pipeline.chunking import CITATION_FIELDS, ChunkingConfig, sha256_bytes
from research_pipeline.config import PipelineConfig
from research_pipeline.datasets import ARTIFACTS, load_active_dataset
from research_pipeline.extraction import clean_extracted_text
from research_pipeline.ingestion import load_manifest
from research_pipeline.pipeline import run_pipeline
from research_pipeline.tokenization import LocalTokenizer


def verify_sources(dataset, config):
    """Check source pages independently of the chunk-builder and dataset validator."""
    lookup = {(page.paper_id, page.page_number): page for page in dataset.pages}
    for paper in dataset.papers:
        reader = PdfReader(config.resolve(Path(paper.source_path)), strict=False)
        assert len(reader.pages) == dataset.manifest["page_counts"][paper.paper_id]
        for number, raw_page in enumerate(reader.pages, 1):
            assert lookup[paper.paper_id, number].text == clean_extracted_text(raw_page.extract_text())
    coverage = {key: set() for key, page in lookup.items() if page.text.strip()}
    for chunk in dataset.chunks:
        source = lookup[chunk.paper_id, chunk.page_number]
        assert chunk.text == source.text[chunk.start_character:chunk.end_character]
        assert all(getattr(source, field) == getattr(chunk, field) for field in CITATION_FIELDS)
        coverage[chunk.paper_id, chunk.page_number].update(range(chunk.start_character, chunk.end_character))
    for key, positions in coverage.items():
        assert positions == set(range(len(lookup[key].text)))


def fixture_tokenizer(path):
    """A real tokenizer implementation with a synthetic vocabulary, not MiniLM."""
    from tokenizers import Tokenizer, models, pre_tokenizers, processors, normalizers
    raw = Tokenizer(models.WordPiece({"[UNK]": 0, "[CLS]": 1, "[SEP]": 2,
                                      "the": 3, "of": 4, "and": 5}, unk_token="[UNK]"))
    raw.normalizer = normalizers.NFC()
    raw.pre_tokenizer = pre_tokenizers.Whitespace()
    raw.post_processor = processors.TemplateProcessing(
        single="[CLS] $A [SEP]", special_tokens=[("[CLS]", 1), ("[SEP]", 2)])
    raw.save(str(path))
    return LocalTokenizer.from_file(path, "test/local-wordpiece", "fixture-v1")


def main():
    config = PipelineConfig()
    papers = load_manifest(config.resolve(config.manifest_path), config.repository_root)
    pdf_hashes = {paper.paper_id: sha256_bytes(config.resolve(Path(paper.source_path)).read_bytes())
                  for paper in papers}
    results = {}
    with tempfile.TemporaryDirectory(prefix="pr3-corpus-") as directory:
        root = Path(directory)
        tokenizer = fixture_tokenizer(root / "tokenizer.json")
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network prohibited")), \
             patch.object(socket.socket, "connect_ex", side_effect=AssertionError("network prohibited")):
            for profile in ("boundary_characters", "fixed_characters", "tokenizer"):
                settings = ChunkingConfig(profile=profile)
                run_root, pointer = root / profile / "runs", root / profile / "active.json"
                options = dict(run_root=run_root, pointer_path=pointer,
                               tokenizer=tokenizer if profile == "tokenizer" else None)
                first = run_pipeline(config, settings, **options)
                assert first["outcome"] == "success"
                dataset = load_active_dataset(run_root, pointer)
                assert len(dataset.pages) == 104 and len(dataset.papers) == 5
                verify_sources(dataset, config)
                names = (*ARTIFACTS, "run_manifest.json")
                before = {name: (dataset.directory / name).read_bytes() for name in names}
                pointer_bytes = pointer.read_bytes()
                second = run_pipeline(config, settings, **options)
                assert first == second and pointer.read_bytes() == pointer_bytes
                assert before == {name: (dataset.directory / name).read_bytes() for name in names}
                if profile == "tokenizer":
                    assert all(tokenizer.counts(chunk.text) == (chunk.content_token_count,
                               chunk.input_token_count) for chunk in dataset.chunks)
                results[profile] = {"papers": len(dataset.papers), "pages": len(dataset.pages),
                                    "chunks": len(dataset.chunks), "generation": dataset.directory.name,
                                    "artifact_hashes": {name: sha256_bytes(content) for name, content in before.items()},
                                    "exact_reconstruction": True, "complete_coverage": True,
                                    "byte_identical_repeats": True}
        assert pdf_hashes == {paper.paper_id: sha256_bytes(config.resolve(Path(paper.source_path)).read_bytes())
                             for paper in papers}
    print(json.dumps({"profiles": results, "network_blocked": True, "source_pdfs_unchanged": True,
                      "tokenizer_evidence": "synthetic local WordPiece; real MiniLM asset not tested"}, indent=2))


if __name__ == "__main__":
    main()
