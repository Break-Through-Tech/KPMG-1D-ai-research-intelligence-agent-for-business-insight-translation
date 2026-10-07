"""Actual local tokenizer fixtures exercise budget overhead and source offsets."""

import importlib
from pathlib import Path
import tempfile
import unittest

from research_pipeline.chunking import ChunkingConfig, chunk_page
from tests.pr3_fixtures import page

try:
    from tokenizers import Tokenizer, models, pre_tokenizers, processors, normalizers
except ImportError:
    Tokenizer = None


@unittest.skipIf(Tokenizer is None, "optional requirements-tokenizers.txt not installed")
class TokenizerTests(unittest.TestCase):
    def setUp(self):
        try:
            self.api = importlib.import_module("research_pipeline.tokenization")
        except ImportError:
            self.fail("PR3 local tokenizer adapter is not implemented")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "tokenizer.json"
        raw = Tokenizer(models.WordPiece({"[UNK]": 0, "[CLS]": 1, "[SEP]": 2,
                                          "a": 3, "b": 4, "c": 5, "é": 6}, unk_token="[UNK]"))
        raw.pre_tokenizer = pre_tokenizers.Whitespace()
        raw.normalizer = normalizers.NFC()
        raw.post_processor = processors.TemplateProcessing(
            single="[CLS] $A [SEP]", special_tokens=[("[CLS]", 1), ("[SEP]", 2)])
        raw.enable_truncation(max_length=3)
        raw.enable_padding(length=12)
        raw.save(str(self.path))
        self.tokenizer = self.api.LocalTokenizer.from_file(self.path, "test/local-wordpiece", "fixture-v1")

    def config(self, **changes):
        return ChunkingConfig(profile="tokenizer", token_budget=3, token_overlap=1,
                              max_input_tokens=5, **changes)

    def test_truncation_padding_disabled_and_special_tokens_counted(self):
        self.assertEqual(self.tokenizer.counts("a b c a b"), (5, 7))
        chunks = chunk_page(page("a b c a b c"), self.config(), self.tokenizer)
        self.assertTrue(all(c.content_token_count <= 3 and c.input_token_count <= 5 for c in chunks))
        self.assertEqual(chunks[0].text, "a b c")
        self.assertEqual(chunks[1].start_character, 4)

    def test_unicode_normalization_preserves_original_source_substrings(self):
        source = page("a e\u0301 😀 漢字 b c " * 4)
        chunks = chunk_page(source, self.config(), self.tokenizer)
        covered = set()
        for chunk in chunks:
            self.assertEqual(chunk.text, source.text[chunk.start_character:chunk.end_character])
            self.assertEqual((chunk.content_token_count, chunk.input_token_count),
                             self.tokenizer.counts(chunk.text))
            covered.update(range(chunk.start_character, chunk.end_character))
        self.assertEqual(covered, set(range(len(source.text))))

    def test_tiny_and_near_budget_overlap_advance_with_sparse_offsets(self):
        for budget in (1, 2, 3):
            for overlap in range(budget):
                config = ChunkingConfig(profile="tokenizer", token_budget=budget,
                                        token_overlap=overlap, max_input_tokens=budget + 2)
                source = page("a     b\n\nc " * 5)
                chunks = chunk_page(source, config, self.tokenizer)
                covered = set()
                for chunk in chunks:
                    covered.update(range(chunk.start_character, chunk.end_character))
                self.assertEqual(covered, set(range(len(source.text))))
                self.assertTrue(all(a.start_character < b.start_character
                                    for a, b in zip(chunks, chunks[1:])))

    def test_impossible_special_token_budget_fails_instead_of_truncating(self):
        config = ChunkingConfig(profile="tokenizer", token_budget=1,
                                token_overlap=0, max_input_tokens=2)
        with self.assertRaises(ValueError):
            chunk_page(page("a"), config, self.tokenizer)

    def test_zero_overlap_is_contiguous_and_long_unknown_word_is_not_rewritten(self):
        config = ChunkingConfig(profile="tokenizer", token_budget=2,
                                token_overlap=0, max_input_tokens=4)
        source = page("a " + "x" * 500 + " b c")
        chunks = chunk_page(source, config, self.tokenizer)
        self.assertEqual("".join(c.text for c in chunks), source.text)

    def test_provenance_has_asset_hash_library_and_declared_identity_without_paths(self):
        provenance = self.tokenizer.provenance()
        self.assertEqual(provenance["model_id"], "test/local-wordpiece")
        self.assertEqual(provenance["revision"], "fixture-v1")
        self.assertEqual(len(provenance["asset_sha256"]), 64)
        self.assertNotIn(str(self.directory.name), str(provenance))
        self.assertIn("library_version", provenance)

    def test_bad_local_asset_or_missing_identity_fail_clearly(self):
        self.path.write_text("not tokenizer json", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.api.LocalTokenizer.from_file(self.path, "test", "v1")
        with self.assertRaises(ValueError):
            self.api.LocalTokenizer.from_file(self.path, "", "v1")

    def test_local_asset_mutation_is_detected_before_or_after_processing(self):
        from research_pipeline.pipeline import _tokenizer_sources, _verify_sources
        snapshot = _tokenizer_sources(self.tokenizer)
        self.path.write_bytes(self.path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "source changed"):
            _tokenizer_sources(self.tokenizer)
        with self.assertRaisesRegex(ValueError, "source input changed"):
            _verify_sources(snapshot)


class MissingTokenizerTests(unittest.TestCase):
    def test_tokenizer_profile_never_silently_uses_characters(self):
        with self.assertRaisesRegex(ValueError, "local tokenizer"):
            chunk_page(page(), ChunkingConfig(profile="tokenizer"))
