"""Query: read the Chroma tables (`papers` and `chunks`) for the UI. Read-only, no embedding model."""

import chromadb
from fastapi import APIRouter, HTTPException, Query

from api.pipeline.store import INDEXING_CONFIG

router = APIRouter()


def _collection(name):
    """A Chroma collection by name, or None if it hasn't been created yet."""
    db = chromadb.PersistentClient(path=str(INDEXING_CONFIG.resolve(INDEXING_CONFIG.chroma_directory)))
    if name not in [c.name for c in db.list_collections()]:
        return None
    return db.get_collection(name)


def _row(identifier, document, metadata):
    """One paper as the UI sees it: id, the embedded text (title + abstract) and every metadata field."""
    return {"id": identifier, "document": document, **metadata}


def _vector(embedding):
    """Chroma returns numpy arrays; send plain floats, rounded to keep the response small."""
    return [round(float(value), 5) for value in embedding]


@router.get("/papers")
def list_papers(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    """All papers in the main table, newest first, paginated."""
    collection = _collection(INDEXING_CONFIG.papers_collection)
    if collection is None:
        return {"total": 0, "limit": limit, "offset": offset, "items": []}
    stored = collection.get(include=["documents", "metadatas"])
    rows = sorted((_row(*row) for row in zip(stored["ids"], stored["documents"], stored["metadatas"])),
                  key=lambda r: (r["published"], r["id"]), reverse=True)
    return {"total": len(rows), "limit": limit, "offset": offset, "items": rows[offset:offset + limit]}


@router.get("/papers/{paper_id}")
def get_paper(paper_id: str):
    """One paper from the main table by its arXiv id (e.g. 2609.35732v1)."""
    collection = _collection(INDEXING_CONFIG.papers_collection)
    stored = collection.get(ids=[paper_id], include=["documents", "metadatas"]) if collection else {"ids": []}
    if not stored["ids"]:
        raise HTTPException(404, f"Paper {paper_id} not found")
    return _row(stored["ids"][0], stored["documents"][0], stored["metadatas"][0])


@router.get("/papers/{paper_id}/embeddings")
def get_paper_embeddings(paper_id: str):
    """Every vector stored for one paper: its paper-level embedding (title + abstract)
    and each passage embedding from the chunks table, in reading order."""
    papers = _collection(INDEXING_CONFIG.papers_collection)
    paper = papers.get(ids=[paper_id], include=["documents", "metadatas", "embeddings"]) if papers else {"ids": []}
    if not paper["ids"]:
        raise HTTPException(404, f"Paper {paper_id} not found")

    chunks = _collection(INDEXING_CONFIG.chunks_collection)
    stored = (chunks.get(where={"paper_id": paper_id}, include=["documents", "metadatas", "embeddings"])
              if chunks else {"ids": [], "documents": [], "metadatas": [], "embeddings": []})
    passages = sorted(({
        "id": identifier,
        "text": document,
        "page_number": metadata["page_number"],
        "start_character": metadata["start_character"],
        "end_character": metadata["end_character"],
        "embedding": _vector(embedding),
    } for identifier, document, metadata, embedding in zip(
        stored["ids"], stored["documents"], stored["metadatas"], stored["embeddings"])),
        key=lambda p: (p["page_number"], p["start_character"]))

    paper_vector = _vector(paper["embeddings"][0])
    return {
        "paper_id": paper_id,
        "embedding_model": paper["metadatas"][0]["embedding_model"],
        "dimensions": len(paper_vector),
        "paper": {"text": paper["documents"][0], "embedding": paper_vector},
        "passages": passages,
    }
