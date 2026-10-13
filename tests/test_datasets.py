"""Corruption and filesystem failures must not select damaged generations."""

from dataclasses import replace
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_pipeline.chunking import ChunkingConfig, build_chunks, profile_record, sha256_bytes
from research_pipeline.storage import write_json, write_jsonl, read_json
from tests.pr3_fixtures import page, paper


class DatasetTests(unittest.TestCase):
    def setUp(self):
        try:
            self.api = importlib.import_module("research_pipeline.datasets")
        except ImportError:
            self.fail("PR3 generation publisher/loader is not implemented")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.run_root = self.root / "runs"
        self.pointer = self.root / "active.json"
        self.config = ChunkingConfig(profile="fixed_characters", size=6, overlap=2)
        self.source = page()

    def stage(self, name="staging", source=None):
        location = self.run_root / name
        location.mkdir(parents=True)
        source = source or self.source
        chunks = build_chunks([source], [paper()], self.config)
        write_jsonl(location / "papers.jsonl", [paper().to_dict()])
        write_jsonl(location / "pages.jsonl", [source.to_dict()])
        write_jsonl(location / "chunks.jsonl", [chunk.to_dict() for chunk in chunks])
        report = {"outcome": "success", "pages_loaded": 1, "chunks_written": len(chunks),
                  "storage_round_trip_valid": True, "unique_chunk_ids": len(chunks),
                  "requested_paper_ids": [paper().paper_id], "included_paper_ids": [paper().paper_id],
                  "excluded_paper_ids": [], "blank_pages": [], "whitespace_chunk_count": 0,
                  "maximum_chunk_characters": max(len(chunk.text) for chunk in chunks),
                  "chunk_counts_by_paper": {paper().paper_id: len(chunks)},
                  "tokenizer_validation": "not_requested", "source_failures": {
                      "missing_pdfs": [], "parsing_failures": [], "papers_without_usable_text": [],
                      "missing_page_papers": []}}
        write_json(location / "quality_report.json", report)
        self.api.write_run_manifest(location, profile_record(self.config),
                                    {"input_mode": "existing_pages", "source_hashes": {"manifest": "a" * 64, "pages": "b" * 64},
                                     "dependencies": {"python": "fixture"}}, "success")
        return location

    def publish(self):
        self.api.publish_dataset(self.stage(), self.run_root, self.pointer)
        return self.api.load_active_dataset(self.run_root, self.pointer)

    def resign(self, location):
        # Simulate valid hashes over corrupt semantics, not just byte corruption.
        manifest = read_json(location / "run_manifest.json")
        for name, details in manifest["artifacts"].items():
            details["sha256"] = sha256_bytes((location / name).read_bytes())
        write_json(location / "run_manifest.json", manifest)
        return sha256_bytes((location / "run_manifest.json").read_bytes())

    def test_roundtrip_and_idempotent_publication_are_complete(self):
        dataset = self.publish()
        before = self.pointer.read_bytes()
        self.api.publish_dataset(self.stage("again"), self.run_root, self.pointer)
        self.assertEqual(before, self.pointer.read_bytes())
        self.assertEqual([chunk.text for chunk in dataset.chunks], ["abcdef", "efghij"])
        self.assertEqual(len(self.api.load_passages(self.run_root, self.pointer)), 2)
        self.assertEqual(self.api.load_passages(self.run_root, self.pointer,
                                              paper_ids=["2608.20318v1"]), [])

    def test_modified_or_missing_artifact_is_rejected(self):
        dataset = self.publish()
        path = dataset.directory / "chunks.jsonl"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            self.api.load_active_dataset(self.run_root, self.pointer)
        path.unlink()
        with self.assertRaises((OSError, ValueError)):
            self.api.load_active_dataset(self.run_root, self.pointer)

    def test_semantic_corruption_is_rejected_even_with_new_hashes(self):
        for field, value in (("text", "wrong!"), ("title", "Wrong title"),
                             ("start_character", 1), ("schema_version", 9),
                             ("chunk_id", "not-content-id"), ("chunking_profile_sha256", "b" * 64)):
            with self.subTest(field=field):
                location = self.stage("corrupt-" + field)
                records = [chunk.to_dict() for chunk in build_chunks([page()], [paper()], self.config)]
                records[0][field] = value
                write_jsonl(location / "chunks.jsonl", records)
                self.resign(location)
                with self.assertRaises(ValueError):
                    self.api.publish_dataset(location, self.run_root, self.pointer)

    def test_incomplete_unsupported_or_inconsistent_manifest_is_rejected(self):
        for change in ("missing", "schema", "coverage", "counts", "algorithm", "provenance"):
            with self.subTest(change=change):
                location = self.stage("manifest-" + change)
                manifest = read_json(location / "run_manifest.json")
                if change == "missing":
                    del manifest["artifacts"]["pages.jsonl"]
                elif change == "schema":
                    manifest["schema_version"] = 2
                elif change == "coverage":
                    manifest["included_paper_ids"] = []
                elif change == "counts":
                    manifest["artifacts"]["chunks.jsonl"]["record_count"] += 1
                elif change == "algorithm":
                    manifest["chunking"]["algorithm_version"] = "future-v99"
                else:
                    del manifest["provenance"]["source_hashes"]
                write_json(location / "run_manifest.json", manifest)
                with self.assertRaises(ValueError):
                    self.api.publish_dataset(location, self.run_root, self.pointer)

    def test_pointer_traversal_absolute_paths_and_symlink_generations_rejected(self):
        for value in ("../outside", str(self.root), "a" * 64):
            with self.subTest(value=value):
                self.run_root.mkdir(exist_ok=True)
                if value == "a" * 64:
                    (self.run_root / value).symlink_to(self.root, target_is_directory=True)
                write_json(self.pointer, {"schema_version": 1, "generation": value,
                                          "run_manifest_sha256": "a" * 64})
                with self.assertRaises(ValueError):
                    self.api.load_active_dataset(self.run_root, self.pointer)

    def test_symlinked_artifact_is_rejected(self):
        location = self.stage()
        artifact = location / "pages.jsonl"
        saved = self.root / "outside-pages.jsonl"
        artifact.rename(saved)
        artifact.symlink_to(saved)
        with self.assertRaises(ValueError):
            self.api.publish_dataset(location, self.run_root, self.pointer)

    def test_directory_and_pointer_failures_preserve_previous_selected_dataset(self):
        prior = self.publish()
        before_pointer = self.pointer.read_bytes()
        before_chunks = (prior.directory / "chunks.jsonl").read_bytes()
        original_rename = Path.rename
        original_replace = Path.replace
        for operation in ("directory", "pointer"):
            with self.subTest(operation=operation):
                candidate = self.stage("failure-" + operation, page("different content"))
                def failing_rename(path, destination):
                    if path == candidate:
                        raise OSError("injected directory failure")
                    return original_rename(path, destination)
                def failing_replace(path, destination):
                    if Path(destination) == self.pointer:
                        raise OSError("injected pointer failure")
                    return original_replace(path, destination)
                with patch.object(Path, "rename", failing_rename if operation == "directory" else original_rename):
                    with patch.object(Path, "replace", failing_replace if operation == "pointer" else original_replace):
                        with self.assertRaises(OSError):
                            self.api.publish_dataset(candidate, self.run_root, self.pointer)
                self.assertEqual(self.pointer.read_bytes(), before_pointer)
                self.assertEqual((prior.directory / "chunks.jsonl").read_bytes(), before_chunks)
                self.api.load_active_dataset(self.run_root, self.pointer)

    def test_existing_generation_corruption_is_not_overwritten(self):
        prior = self.publish()
        artifact = prior.directory / "pages.jsonl"
        artifact.write_bytes(b"corrupted")
        with self.assertRaises(ValueError):
            self.api.publish_dataset(self.stage("same-input"), self.run_root, self.pointer)
        self.assertEqual(artifact.read_bytes(), b"corrupted")

    def test_missing_mode_specific_source_hashes_are_rejected(self):
        for mode in ("existing_pages", "pdf_pipeline"):
            location = self.stage("provenance-" + mode)
            manifest = read_json(location / "run_manifest.json")
            manifest["provenance"]["input_mode"] = mode
            manifest["provenance"]["source_hashes"] = {"manifest": "a" * 64}
            manifest["provenance"]["dependencies"] = {"python": "fixture", "pypdf": "fixture", "fonttools": "fixture"}
            write_json(location / "run_manifest.json", manifest)
            with self.assertRaisesRegex(ValueError, "source hash"):
                self.api.load_generation(location)

    def test_interruption_before_pointer_selection_preserves_active_generation(self):
        prior = self.publish()
        pointer_bytes = self.pointer.read_bytes()
        candidate = self.stage("interrupt", page("new source content"))
        with patch("research_pipeline.datasets.write_json", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.api.publish_dataset(candidate, self.run_root, self.pointer)
        self.assertEqual(self.pointer.read_bytes(), pointer_bytes)
        self.assertEqual(self.api.load_active_dataset(self.run_root, self.pointer).directory, prior.directory)

    def test_rehashed_contradictory_or_incomplete_quality_report_is_rejected(self):
        changes = {"included_paper_ids": [], "excluded_paper_ids": ["2608.20318v1"],
                   "requested_paper_ids": [], "unique_chunk_ids": 0, "whitespace_chunk_count": 1,
                   "blank_pages": [{"paper_id": paper().paper_id, "page_number": 1}],
                   "maximum_chunk_characters": 100, "chunk_counts_by_paper": {},
                   "tokenizer_validation": "local_asset_counts_verified", "source_failures": {
                       "missing_pdfs": [paper().paper_id], "parsing_failures": [],
                       "papers_without_usable_text": [], "missing_page_papers": []}}
        for field, value in changes.items():
            location = self.stage("report-" + field)
            report = read_json(location / "quality_report.json")
            report[field] = value
            write_json(location / "quality_report.json", report)
            self.resign(location)
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.api.load_generation(location)
        location = self.stage("missing-report-field")
        report = read_json(location / "quality_report.json")
        del report["unique_chunk_ids"]
        write_json(location / "quality_report.json", report)
        self.resign(location)
        with self.assertRaises(ValueError):
            self.api.load_generation(location)

    def test_missing_mode_specific_dependency_provenance_is_rejected(self):
        for mode in ("existing_pages", "pdf_pipeline"):
            location = self.stage("dependency-" + mode)
            manifest = read_json(location / "run_manifest.json")
            provenance = manifest["provenance"]
            provenance["input_mode"] = mode
            provenance["source_hashes"]["pdf:" + paper().paper_id] = "b" * 64
            provenance["dependencies"] = {"unrelated": "anything"}
            write_json(location / "run_manifest.json", manifest)
            with self.assertRaisesRegex(ValueError, "dependency"):
                self.api.load_generation(location)


if __name__ == "__main__":
    unittest.main()
