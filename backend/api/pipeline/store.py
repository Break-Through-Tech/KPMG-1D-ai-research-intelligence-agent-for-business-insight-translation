"""Store: turn downloaded papers into validated passages and sync them into ChromaDB."""

from pathlib import Path

from fastapi import APIRouter, HTTPException

from api.pipeline import pipeline_lock
from indexing_pipeline.config import IndexingConfig
from indexing_pipeline.indexing import PaperIndexer
from research_pipeline.config import PipelineConfig
from research_pipeline.pipeline import run_chunking
from retrieval_pipeline.config import RetrievalConfig

INDEXING_CONFIG = IndexingConfig(chroma_directory=Path("data/database/chroma"))

router = APIRouter()


@router.post("/papers/store")
def store_papers():
    """Publish validated passages from the downloaded papers and embed papers + passages into Chroma."""
    if not pipeline_lock.acquire(blocking=False):
        raise HTTPException(409, "The pipeline is already running")
    try:
        retrieval_config = RetrievalConfig()
        result = run_chunking(PipelineConfig(repository_root=retrieval_config.repository_root,
                                             manifest_path=retrieval_config.manifest_path,
                                             extracted_pages_path=retrieval_config.pages_path))
        if not result["artifacts_published"]:
            raise HTTPException(500, "Page corpus did not produce a complete validated passage generation")

        indexer = PaperIndexer(INDEXING_CONFIG)
        papers_updated = indexer.index_papers()
        chunks_updated = indexer.index_chunks()
        return {
            "generation": result["generation"],
            "papers": {"updated": papers_updated, "total": indexer.papers.count()},
            "chunks": {"updated": chunks_updated, "total": indexer.chunks.count()},
        }
    finally:
        pipeline_lock.release()
