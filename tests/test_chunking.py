"""Protect exact source reconstruction, coverage and deterministic character chunks."""

from dataclasses import replace
import importlib
import unittest

from tests.pr3_fixtures import page, paper


class ChunkingTests(unittest.TestCase):
    def setUp(self):
        try:
            self.api = importlib.import_module("research_pipeline.chunking")
        except ImportError:
            self.fail("PR3 chunking API is not implemented")

    def config(self, **changes):
        return self.api.ChunkingConfig(profile="fixed_characters", size=6, overlap=2, **changes)

    def assert_coverage(self, source, chunks):
        covered = set()
        for chunk in chunks:
            self.assertEqual(chunk.text, source.text[chunk.start_character:chunk.end_character])
            covered.update(range(chunk.start_character, chunk.end_character))
        self.assertEqual(covered, set(range(len(source.text))))

    def test_fixed_windows_have_exact_overlap_and_source_offsets(self):
        chunks = self.api.chunk_page(page(), self.config())
        self.assertEqual([(c.start_character, c.end_character, c.text) for c in chunks],
                         [(0, 6, "abcdef"), (4, 10, "efghij")])
        self.assert_coverage(page(), chunks)

    def test_boundary_profile_prefers_paragraph_end_without_losing_text(self):
        source = page("alpha\n\nbeta gamma delta")
        config = self.api.ChunkingConfig(size=15, overlap=2)
        chunks = self.api.chunk_page(source, config)
        self.assertEqual(chunks[0].text, "alpha\n\n")
        for previous, following in zip(chunks, chunks[1:]):
            self.assertEqual(following.start_character, previous.end_character - 2)
        self.assert_coverage(source, chunks)

    def test_unicode_oversized_segments_and_whitespace_are_lossless(self):
        for text in ("😀e\u0301漢字" * 9, "a" * 37, "a" + " " * 19 + "b", " a\n\nb\t c "):
            for profile in ("fixed_characters", "boundary_characters"):
                with self.subTest(text=text, profile=profile):
                    config = self.api.ChunkingConfig(profile=profile, size=6, overlap=5)
                    chunks = self.api.chunk_page(page(text), config)
                    self.assert_coverage(page(text), chunks)
                    self.assertTrue(all(0 < len(c.text) <= 6 for c in chunks))
                    self.assertEqual(len(chunks), len({c.chunk_id for c in chunks}))

    def test_empty_and_whitespace_pages_produce_no_chunks(self):
        for text in ("", " \n\t"):
            self.assertEqual(self.api.chunk_page(page(text), self.config()), [])

    def test_small_zero_overlap_and_near_size_overlap_advance(self):
        for size in (1, 2, 6):
            for overlap in range(size):
                for profile in ("fixed_characters", "boundary_characters"):
                    config = self.api.ChunkingConfig(profile=profile, size=size, overlap=overlap)
                    self.assert_coverage(page(), self.api.chunk_page(page(), config))

    def test_invalid_settings_reject_booleans_and_bad_budgets(self):
        for changes in ({"size": 0}, {"size": True}, {"overlap": -1},
                        {"size": 5, "overlap": 5}, {"profile": "semantic"},
                        {"token_budget": 0}, {"token_overlap": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.api.ChunkingConfig(**changes)

    def test_ids_repeat_and_change_with_text_metadata_or_configuration(self):
        config = self.config()
        baseline = self.api.chunk_page(page(), config)[0]
        self.assertEqual(baseline, self.api.chunk_page(page(), config)[0])
        for source, settings in ((page("abcdefghiX"), config),
                                 (replace(page(), title="New title"), config),
                                 (page(), replace(config, overlap=1))):
            self.assertNotEqual(baseline.chunk_id, self.api.chunk_page(source, settings)[0].chunk_id)

    def test_json_roundtrip_preserves_citation_and_offsets(self):
        chunk = self.api.chunk_page(page(), self.config())[0]
        self.assertEqual(self.api.CitationChunk.from_dict(chunk.to_dict()), chunk)
        for field in ("paper_id", "title", "authors", "published", "pdf_url", "page_number"):
            self.assertEqual(chunk.to_dict()[field], page().to_dict()[field])
        self.assertIsNone(chunk.content_token_count)

    def test_chunk_authors_cannot_be_mutated_and_required_fields_are_not_optional(self):
        chunk = self.api.chunk_page(page(), self.config())[0]
        with self.assertRaises(TypeError):
            chunk.authors[0] = "changed author"
        for field in ("content_token_count", "input_token_count"):
            record = chunk.to_dict()
            del record[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.api.CitationChunk.from_dict(record)

    def test_invalid_chunk_records_reject_schema_offsets_hashes_and_nonobjects(self):
        record = self.api.chunk_page(page(), self.config())[0].to_dict()
        for value in (None, [], 2, {**record, "schema_version": 2},
                      {**record, "schema_version": True}, {**record, "start_character": True},
                      {**record, "end_character": 0}, {**record, "page_text_sha256": "bad"},
                      {**record, "text": ""}, {**record, "input_token_count": False}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.api.CitationChunk.from_dict(value)

    def test_build_rejects_duplicate_gap_unknown_or_conflicting_pages(self):
        for sources in ([page(), page()], [page(number=2)],
                        [page(), replace(page(number=2), title="Wrong title")],
                        [replace(page(), paper_id="2608.20318v1",
                                 pdf_url="https://arxiv.org/pdf/2608.20318v1")]):
            with self.subTest(sources=sources), self.assertRaises(ValueError):
                self.api.build_chunks(sources, [paper()], self.config())

    def test_build_sorts_pages_and_validation_detects_missing_coverage(self):
        sources = [page(number=2), page()]
        chunks = self.api.build_chunks(sources, [paper()], self.config())
        self.assertEqual(chunks, self.api.build_chunks(list(reversed(sources)), [paper()], self.config()))
        self.api.validate_chunks(chunks, sources, [paper()])
        with self.assertRaises(ValueError):
            self.api.validate_chunks(chunks[1:], sources, [paper()])

    def test_validation_rejects_text_and_id_tampering(self):
        source = page()
        chunks = self.api.chunk_page(source, self.config())
        for replacement in (replace(chunks[0], text="wrong!"),
                            replace(chunks[0], chunk_id="wrong"),
                            replace(chunks[0], title="Wrong title")):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                self.api.validate_chunks([replacement, *chunks[1:]], [source], [paper()])


if __name__ == "__main__":
    unittest.main()
