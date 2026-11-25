"""Shared embedding model instance for API searches and indexing."""

import threading

from indexing_pipeline.config import IndexingConfig
from indexing_pipeline.indexing import build_embedding_function

_embedding_function = None
_embedding_lock = threading.Lock()


def get_embedding_function(config: IndexingConfig):
    """Load the configured embedding model once for the lifetime of the backend."""

    global _embedding_function
    with _embedding_lock:
        if _embedding_function is None:
            _embedding_function = build_embedding_function(config)
    return _embedding_function
