"""Search_Chroma: semantic search over the passages table (`chunks`). This is the agent's retrieval tool.

The query is embedded with the same model the indexer used, then Chroma returns the k nearest
passages (cosine) from the active generation. Each result carries the vectors that were compared,
so the UI can show exactly which embeddings the agent used.
"""

import json
import threading

import chromadb
from fastapi import APIRouter, HTTPException, Query

from api.Query_Chroma import _vector
from api.embedding import get_embedding_function
from api.pipeline.store import INDEXING_CONFIG
from indexing_pipeline.indexing import query_embedding_text

TOP_K = 6  # passages returned per search

router = APIRouter()

_embedder = None
_embedder_lock = threading.Lock()


class SearchUnavailable(RuntimeError):
    """The vector database can't answer searches yet (not indexed, or indexed with another model)."""


def _embed(text):
    """Embed one text with the indexing model. The model is loaded once, on the first search."""
    global _embedder
    with _embedder_lock:
        if _embedder is None:
            _embedder = get_embedding_function(INDEXING_CONFIG)
    query = query_embedding_text(text, INDEXING_CONFIG.embedding_provider)
    return [float(value) for value in _embedder([query])[0]]


def warm_up():
    """Load the embedding model ahead of the first question (loading it cold can take a minute or more)."""
    try:
        _embed("warm-up")
    except Exception as error:  # the first search will retry and report the problem to the agent
        print(f"Embedding model not loaded at startup: {error}")


def _active_generation():
    """The passage generation that 'Store' indexed last (data/processed/active_run.json)."""
    pointer = INDEXING_CONFIG.resolve(INDEXING_CONFIG.active_pointer)
    if not pointer.exists():
        raise SearchUnavailable("No passages have been published yet. Run Retrieve, then Store.")
    return json.loads(pointer.read_text(encoding="utf-8"))["generation"]


def search_passages(query, k=TOP_K):
    """The k passages closest to `query`, with the query vector and each passage's stored vector."""
    db = chromadb.PersistentClient(path=str(INDEXING_CONFIG.resolve(INDEXING_CONFIG.chroma_directory)))
    if INDEXING_CONFIG.chunks_collection not in [c.name for c in db.list_collections()]:
        raise SearchUnavailable("The passages table doesn't exist yet. Run Store to index the papers.")
    chunks = db.get_collection(INDEXING_CONFIG.chunks_collection)

    query_vector = _embed(query)
    result = chunks.query(query_embeddings=[query_vector], n_results=k,
                          where={"generation": _active_generation()},
                          include=["documents", "metadatas", "distances", "embeddings"])

    metadatas = result["metadatas"][0]
    if any(m["embedding_model"] != INDEXING_CONFIG.embedding_model for m in metadatas):
        raise SearchUnavailable("Passages were embedded with a different model. Run Store to re-index them.")

    passages = [{
        "rank": rank,
        "chunk_id": identifier,
        "paper_id": metadata["paper_id"],
        "title": metadata["title"],
        "page_number": metadata["page_number"],
        "start_character": metadata["start_character"],
        "end_character": metadata["end_character"],
        "pdf_url": metadata["pdf_url"],
        "text": document,
        "score": round(1 - distance, 4),  # cosine similarity
        "embedding": _vector(embedding),
    } for rank, (identifier, metadata, document, distance, embedding) in enumerate(zip(
        result["ids"][0], metadatas, result["documents"][0], result["distances"][0], result["embeddings"][0]), 1)]

    return {
        "query": query,
        "embedding_model": INDEXING_CONFIG.embedding_model,
        "dimensions": len(query_vector),
        "query_embedding": _vector(query_vector),
        "passages": passages,
    }


@router.get("/search")
def search(q: str = Query(min_length=1), k: int = Query(TOP_K, ge=1, le=20)):
    """Run the agent's retrieval directly: the k passages nearest to `q`, with their embeddings."""
    try:
        return search_passages(q, k)
    except SearchUnavailable as error:
        raise HTTPException(503, str(error)) from error
