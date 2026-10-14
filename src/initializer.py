"""Initialization pipeline: download papers, embed them, and answer questions with Claude.

Run from the repository root:  python src/initializer.py
Needs ANTHROPIC_API_KEY in .env (copy .env.example) for the answering step.
"""

import anthropic
from dotenv import load_dotenv
from indexing_pipeline.indexing import PaperIndexer
from retrieval_pipeline.retrieval import PaperRetriever

load_dotenv()  # reads ANTHROPIC_API_KEY from .env


def initialize(n_papers=10):
    """Download the n newest papers + extract their pages, then embed papers and chunks. Returns the indexer."""
    print(f"[1/4] Checking arXiv for the {n_papers} newest papers (new PDFs get downloaded + their pages extracted)...", flush=True)
    new_papers = PaperRetriever().download_latest(n_papers)
    print(f"      {len(new_papers)} new paper(s) added")
    print("[2/4] Loading the embedding model and the vector database (first run downloads the model)...", flush=True)
    indexer = PaperIndexer()
    print(f"[3/4] Embedding papers (title + abstract) with {indexer.config.embedding_model}...", flush=True)
    print(f"      {indexer.index_papers()} new, {indexer.papers.count()} total")
    print("[4/4] Embedding page chunks (can take a minute when there are new papers)...", flush=True)
    print(f"      {indexer.index_chunks()} new, {indexer.chunks.count()} total")
    print("Ready.")
    return indexer


def answer(indexer, question, client=None, k=5):
    """Answer the question using only the k best passages, citing them as [paper_id p.page].
    Returns (answer text, the passages the embedding search retrieved, each with its similarity score)."""
    print("Searching the embeddings for relevant passages...", flush=True)
    passages = indexer.search_two_stage(question, k=k)
    if not passages:
        return "No relevant passages found.", []
    print(f"Asking Claude with {len(passages)} passage(s)...", flush=True)
    context ="\n\n".join(f"[{p['paper_id']} p.{p['page_number']}]\n{p['text']}" for p in passages)
    response = (client or anthropic.Anthropic()).messages.create(
        model="claude-haiku-5-5",
        max_tokens=16000,
        system="Answer the question for a business reader using only the passages given consicely. "
               "Cite each claim as [paper_id p.page]. If the passages don't answer it, say so.",
               
        messages=[{"role": "user", "content": f"Passages:\n\n{context}\n\nQuestion: {question}"}],
    )
    return "".join(block.text for block in response.content if block.type == "text"), passages


if __name__ == "__main__":
    indexer = initialize()
    while question := input("\nQuestion (blank to quit): ").strip():
        text, passages = answer(indexer, question)
        print(f"\nPassages retrieved by {indexer.config.embedding_model} (cosine similarity):")
        for p in passages:
            print(f"  {p['score']:.3f}  [{p['paper_id']} p.{p['page_number']}]  {' '.join(p['text'].split())[:120]}...")
        print(f"\nAnswer:\n{text}")
