"""Corpus comparisons are read-only and reject ambiguous metadata identities."""

import importlib
from pathlib import Path
import tempfile
import unittest


class HandoffTests(unittest.TestCase):
    def setUp(self):
        try:
            self.api = importlib.import_module("research_pipeline.handoff")
        except ImportError:
            self.fail("PR3 corpus coverage handoff is not implemented")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "metadata.csv"

    def test_shared_and_disjoint_ids_are_reported_without_modifying_csv(self):
        contents = "id,title\n2608.20316v1,one\n2609.35770v1,two\n"
        self.path.write_text(contents, encoding="utf-8")
        report = self.api.compare_corpus_ids(["2608.20316v1", "2608.20318v1"], self.path)
        self.assertEqual(report, {"shared_ids": ["2608.20316v1"],
                                  "passages_only_ids": ["2608.20318v1"],
                                  "metadata_only_ids": ["2609.35770v1"]})
        self.assertEqual(self.path.read_text(), contents)

    def test_bad_columns_duplicates_and_noncanonical_ids_are_rejected(self):
        for contents in ("title\none\n", "id\n2608.20316v1\n2608.20316v1\n",
                         "id\n2608.20316V1\n", "id\n\n", "id\n\"\"\n"):
            self.path.write_text(contents, encoding="utf-8")
            if contents == "id\n\n":
                self.assertEqual(self.api.compare_corpus_ids([], self.path)["shared_ids"], [])
            else:
                with self.subTest(contents=contents), self.assertRaises(ValueError):
                    self.api.compare_corpus_ids([], self.path)
