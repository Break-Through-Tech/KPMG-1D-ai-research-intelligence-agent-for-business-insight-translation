import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from indexing_pipeline.config import IndexingConfig
from indexing_pipeline.indexing import (
    E5EmbeddingFunction,
    build_embedding_function,
    query_embedding_text,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from api import Search_Chroma  # noqa: E402


class EmbeddingConfigurationTests(unittest.TestCase):
    def test_e5_large_is_the_default_model(self):
        config = IndexingConfig()

        self.assertEqual(config.embedding_model, "intfloat/e5-large-v2")
        self.assertEqual(config.embedding_provider, "sentence-transformers-e5")

    def test_query_text_gets_e5_prefix_only_for_e5_provider(self):
        self.assertEqual(query_embedding_text("How does it work?", "sentence-transformers-e5"),
                         "query: How does it work?")
        self.assertEqual(query_embedding_text("How does it work?", "sentence-transformers"),
                         "How does it work?")

    def test_e5_embedding_function_prefixes_passages_and_preserves_query_prefix(self):
        embedding_function = E5EmbeddingFunction.__new__(E5EmbeddingFunction)
        with patch.object(
            SentenceTransformerEmbeddingFunction,
            "__call__",
            return_value=[[1.0], [2.0], [3.0]],
        ) as embed:
            result = embedding_function(
                ["indexed text", "query: search text", "passage: already prefixed"]
            )

        embed.assert_called_once_with(
            ["passage: indexed text", "query: search text", "passage: already prefixed"]
        )
        self.assertEqual(result, [[1.0], [2.0], [3.0]])

    def test_factory_builds_e5_function_from_config(self):
        config = IndexingConfig()
        with patch("indexing_pipeline.indexing.E5EmbeddingFunction", return_value="embedder") as factory:
            result = build_embedding_function(config)

        factory.assert_called_once_with(model_name="intfloat/e5-large-v2")
        self.assertEqual(result, "embedder")

    def test_backend_search_embeds_queries_with_e5_prefix(self):
        mock_embedder = Mock(return_value=[[0.1, 0.2]])
        config = SimpleNamespace(
            embedding_provider="sentence-transformers-e5",
            embedding_model="intfloat/e5-large-v2",
        )
        with (
            patch.object(Search_Chroma, "INDEXING_CONFIG", config),
            patch.object(Search_Chroma, "_embedder", mock_embedder),
        ):
            vector = Search_Chroma._embed("How does it work?")

        mock_embedder.assert_called_once_with(["query: How does it work?"])
        self.assertEqual(vector, [0.1, 0.2])


if __name__ == "__main__":
    unittest.main()
