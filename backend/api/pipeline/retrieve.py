"""Retrieve: download the newest arXiv cs.AI papers (PDFs, papers.json, pages.jsonl)."""

from fastapi import APIRouter, HTTPException, Query

from api.pipeline import pipeline_lock
from retrieval_pipeline.config import RetrievalConfig
from retrieval_pipeline.retrieval import PaperRetriever

router = APIRouter()


@router.post("/papers/retrieve")
def retrieve_papers(n: int = Query(10, ge=1, le=100)):
    """Download the n newest cs.AI papers from arXiv.
    (n must be >= 1: the arxiv library treats 0 as "no limit".)"""
    if not pipeline_lock.acquire(blocking=False):
        raise HTTPException(409, "The pipeline is already running")
    try:
        new_papers = PaperRetriever(RetrievalConfig()).download_latest(n)
        return {"new_papers": [p["paper_id"] for p in new_papers]}
    finally:
        pipeline_lock.release()