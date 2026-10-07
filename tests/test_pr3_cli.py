"""Public commands expose honest outcomes without network or legacy-output writes."""

from contextlib import redirect_stdout
import importlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from research_pipeline.storage import write_json, write_jsonl
from tests.pr3_fixtures import page
from tests.test_extraction_cli import write_fixture_pdf, SECOND_RECORD
from tests.test_ingestion import VALID_RECORD


class Pr3CliTests(unittest.TestCase):
    def setUp(self):
        try:
            self.api = importlib.import_module("research_pipeline.cli")
        except ImportError:
            self.fail("PR3 CLI is not implemented")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        write_json(self.root / "data/manifest/papers.json", [VALID_RECORD])
        write_fixture_pdf(self.root / VALID_RECORD["source_path"], ["first page"])

    def invoke(self, command, *options):
        output = io.StringIO()
        with redirect_stdout(output):
            code = self.api.main([command, "--repository-root", str(self.root), *options])
        return code, json.loads(output.getvalue())

    def test_run_inspect_and_coverage_commands_use_existing_contracts(self):
        code, report = self.invoke("run")
        self.assertEqual(code, 0)
        self.assertTrue(report["artifacts_published"])
        code, report = self.invoke("inspect")
        self.assertEqual((code, report["papers"], report["pages"], report["chunks"]), (0, 1, 1, 1))
        csv = self.root / "metadata.csv"
        csv.write_text("id,title\n2609.35770v1,different paper\n", encoding="utf-8")
        code, report = self.invoke("coverage", "--metadata-csv", str(csv))
        self.assertEqual(code, 0)
        self.assertEqual(report["shared_ids"], [])
        self.assertEqual(report["passages_only_ids"], [VALID_RECORD["paper_id"]])

    def test_failures_and_partial_publication_exit_nonzero(self):
        write_json(self.root / "data/manifest/papers.json", [VALID_RECORD, SECOND_RECORD])
        code, report = self.invoke("run")
        self.assertEqual((code, report["artifacts_published"]), (2, False))
        code, report = self.invoke("run", "--allow-partial")
        self.assertEqual((code, report["artifacts_published"]), (2, True))
        code, report = self.invoke("run", "--chunk-size", "0")
        self.assertEqual((code, report["outcome"]), (3, "failure"))
        code, report = self.invoke("run", "--profile", "tokenizer")
        self.assertEqual((code, report["outcome"]), (3, "failure"))

    def test_standalone_module_is_independently_runnable(self):
        write_jsonl(self.root / "data/processed/pages.jsonl", [page().to_dict()])
        completed = subprocess.run([sys.executable, "-m", "research_pipeline.chunking_cli",
                                    "--repository-root", str(self.root)],
                                   capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["artifacts_published"])

    def test_invalid_pages_return_json_failure_and_preserve_previous_pointer(self):
        self.invoke("run")
        pointer = self.root / "data/processed/active_run.json"
        before = pointer.read_bytes()
        write_jsonl(self.root / "data/processed/pages.jsonl", [None])
        code, report = self.invoke("chunk", "--allow-partial")
        self.assertEqual((code, report["outcome"]), (3, "failure"))
        self.assertEqual(pointer.read_bytes(), before)

    @unittest.skipUnless(importlib.util.find_spec("tokenizers"), "optional tokenizer dependency")
    def test_tokenizer_asset_alias_and_containing_run_root_are_rejected(self):
        from tests.validate_pr3_corpus import fixture_tokenizer
        self.invoke("run")
        pointer = self.root / "data/processed/active_run.json"
        prior_pointer = pointer.read_bytes()
        for command in ("run", "chunk"):
            write_jsonl(self.root / "data/processed/pages.jsonl", [page().to_dict()])
            for case in ("same", "hardlink", "symlink", "root"):
                asset_directory = self.root / f"assets-{command}-{case}"
                asset_directory.mkdir()
                asset = asset_directory / "tokenizer.json"
                fixture_tokenizer(asset)
                original = asset.read_bytes()
                alias = self.root / f"tokenizer-{command}-{case}-hardlink.json"
                if case == "symlink":
                    alias.symlink_to(asset)
                else:
                    alias.hardlink_to(asset)
                output_options = (("--run-root", str(asset_directory)) if case == "root" else
                                  ("--active-pointer", str(alias if case in ("hardlink", "symlink") else asset)))
                with self.subTest(command=command, options=output_options):
                    code, _ = self.invoke(command, "--profile", "tokenizer",
                                          "--tokenizer-file", str(asset),
                                          "--tokenizer-model-id", "test/local-wordpiece",
                                          "--tokenizer-revision", "fixture-v1", *output_options)
                    self.assertEqual(code, 3)
                    self.assertEqual(asset.read_bytes(), original)
                    self.assertEqual(pointer.read_bytes(), prior_pointer)
