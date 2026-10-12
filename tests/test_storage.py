"""Atomic storage preserves prior artifacts and cleans failed temporary files."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_pipeline.storage import read_json, read_jsonl, write_json, write_jsonl


class AtomicStorageTests(unittest.TestCase):
    def assert_only_destination_remains(self, path: Path, previous: bytes) -> None:
        self.assertEqual(path.read_bytes(), previous)
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_json_serialization_failure_cleans_temporary_and_preserves_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            path.write_bytes(b"previous json\n")
            with self.assertRaises(TypeError):
                write_json(path, {"bad": object()})
            self.assert_only_destination_remains(path, b"previous json\n")

    def test_jsonl_iterator_failure_cleans_temporary_and_preserves_destination(self) -> None:
        def records():
            yield {"text": "first record"}
            raise RuntimeError("fixture iterator failure")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.jsonl"
            path.write_bytes(b"previous jsonl\n")
            with self.assertRaisesRegex(RuntimeError, "iterator failure"):
                write_jsonl(path, records())
            self.assert_only_destination_remains(path, b"previous jsonl\n")

    def test_jsonl_serialization_failure_cleans_temporary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.jsonl"
            with self.assertRaises(TypeError):
                write_jsonl(path, [{"good": "record"}, {"bad": object()}])
            self.assertFalse(path.exists())
            self.assertEqual(list(path.parent.iterdir()), [])

    def test_replace_failure_preserves_destination_and_cleans_temporary(self) -> None:
        for writer, value in ((write_json, {"new": "json"}), (write_jsonl, [{"new": "jsonl"}])):
            with self.subTest(writer=writer.__name__), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "artifact"
                path.write_bytes(b"previous artifact\n")
                with patch.object(Path, "replace", side_effect=PermissionError("fixture permission denied")):
                    with self.assertRaises(PermissionError):
                        writer(path, value)
                self.assert_only_destination_remains(path, b"previous artifact\n")

    def test_successful_json_and_jsonl_replace_and_preserve_unicode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_path, jsonl_path = root / "artifact.json", root / "artifact.jsonl"
            value = {"text": "café \u03bb", "authors": ["First", "Second"]}
            write_json(json_path, value)
            self.assertEqual(read_json(json_path), value)
            self.assertEqual(write_jsonl(jsonl_path, [value, {"text": ""}]), 2)
            self.assertEqual(read_jsonl(jsonl_path, dict), [value, {"text": ""}])
            self.assertEqual({path.name for path in root.iterdir()}, {"artifact.json", "artifact.jsonl"})


if __name__ == "__main__":
    unittest.main()
