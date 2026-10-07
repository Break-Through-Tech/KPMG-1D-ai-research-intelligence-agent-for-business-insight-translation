"""Optional local fast-tokenizer budgets; no Hub calls or embedding inference."""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

from research_pipeline.chunking import ChunkingConfig, _preferred_end, sha256_bytes


class LocalTokenizer:
    """A local tokenizer with truncation/padding disabled and declared provenance.

    The declared model/revision identifies the intended experiment; a local JSON
    file alone cannot prove it is the official tokenizer for that model.
    """

    def __init__(self, tokenizer, provenance: dict[str, str], source_path: Path):
        self._tokenizer = tokenizer
        self._provenance = dict(provenance)
        self.source_path = source_path

    @classmethod
    def from_file(cls, path: Path, model_id: str, revision: str) -> LocalTokenizer:
        """Load only local JSON and disable hidden truncation and padding.

        Raises ValueError for missing identity or invalid assets, OSError for
        unreadable files, and ValueError with setup guidance if the optional
        tokenizers dependency is absent. No network access occurs.
        """
        if not isinstance(model_id, str) or not model_id.strip() or not isinstance(
                revision, str) or not revision.strip():
            raise ValueError("tokenizer model_id and revision must be nonempty")
        try:
            from tokenizers import Tokenizer
        except ImportError as error:
            raise ValueError("install optional requirements-tokenizers.txt for tokenizer mode") from error
        source_path = Path(path).resolve()
        asset = source_path.read_bytes()
        try:
            tokenizer = Tokenizer.from_str(asset.decode("utf-8"))
        except Exception as error:
            raise ValueError("invalid local tokenizer JSON") from error
        tokenizer.no_truncation()
        tokenizer.no_padding()
        return cls(tokenizer, {"model_id": model_id.strip(), "revision": revision.strip(),
                               "asset_sha256": sha256_bytes(asset), "library": "tokenizers",
                               "library_version": version("tokenizers"),
                               "input_template": "chunk_text_only"}, source_path)

    def provenance(self) -> dict[str, str]:
        """Return a copy of effective identity and exact local asset provenance."""
        return dict(self._provenance)

    def counts(self, text: str) -> tuple[int, int]:
        """Return actual content and complete-input counts without truncation."""
        return (len(self._tokenizer.encode(text, add_special_tokens=False).ids),
                len(self._tokenizer.encode(text, add_special_tokens=True).ids))

    def offsets(self, text: str) -> list[tuple[int, int]]:
        """Original Unicode offsets of content tokens, omitting zero-width tokens."""
        offsets = self._tokenizer.encode(text, add_special_tokens=False).offsets
        if any(not 0 <= start <= end <= len(text) for start, end in offsets):
            raise ValueError("tokenizer produced invalid Unicode source offsets")
        return [(start, end) for start, end in offsets if end > start]

    def window(self, text: str, start: int, config: ChunkingConfig):
        """Choose a verified exact source span and offset-defined token overlap.

        A candidate is measured again after slicing because subword tokenization
        can change at boundaries. Shrink rather than silently truncate if needed.
        """
        remaining = text[start:]
        offsets = self.offsets(remaining)
        hard_end = len(text) if len(offsets) <= config.token_budget else (
            start + offsets[config.token_budget - 1][1])
        end = _preferred_end(text, start, hard_end, start + 1)
        while end > start:
            counts = self.counts(text[start:end])
            if counts[0] <= config.token_budget and counts[1] <= config.max_input_tokens:
                break
            end -= 1
        if end <= start:
            raise ValueError("token budget cannot encode even one source character with special tokens")
        if config.token_overlap == 0:
            next_start = end
        else:
            selected_offsets = self.offsets(text[start:end])
            next_start = end if not selected_offsets else max(
                start + 1, start + selected_offsets[-min(config.token_overlap,
                                                        len(selected_offsets))][0])
        return end, next_start, counts
