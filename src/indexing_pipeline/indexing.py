"""Stage 1: Paper Search (abstracts)

Embeds each paper's title + abstract from data/downloaded/metadata.csv into the ChromaDB collection
"papers" (saved in data/chroma/), then searches it with a natural-language question.

Run retrieval_pipeline/retrieval.py first to download papers.
"""

import csv
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from indexing_pipeline.config import IndexingConfig


class PaperIndexer:
    """Indexes each paper's title + abstract in ChromaDB and searches it."""
    def __init__(self, config=IndexingConfig()):
        # Input metadata (from retrieval.py) and where the vector database is saved (set in config.py)
        self.config = config
        self.meta_path = config.resolve(config.metadata_path)
        self.chroma_dir = config.resolve(config.chroma_directory)

        # Embedding model: turns text into 384 numbers that represent its meaning, fast and lightweight
        self.embed_fn = SentenceTransformerEmbeddingFunction(model_name=config.embedding_model)

        # Vector database on disk; "papers" = one entry per paper, compared by cosine similarity
        self.db = chromadb.PersistentClient(path=str(self.chroma_dir))
        self.papers = self.db.get_or_create_collection(
            config.papers_collection, embedding_function=self.embed_fn, configuration={"hnsw": {"space": "cosine"}}
        )

    def index_papers(self):
        """Add every paper in metadata.csv that isn't in the collection yet.
        Returns the number of papers added (0 if everything was already indexed)."""
        with open(self.meta_path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        existing = set(self.papers.get(ids=[r["id"] for r in rows])["ids"]) if rows else set()
        new_rows = [r for r in rows if r["id"] not in existing]
        if new_rows:
            self.papers.add(
                ids=[r["id"] for r in new_rows],
                documents=[f"{r['title']}. {r['abstract']}" for r in new_rows],  # the text that gets embedded
                metadatas=[{"title": r["title"], "url": r["url"], "published": r["published"]} for r in new_rows],
            )
        return len(new_rows)

    def search(self, question, k=5):
        """Return the k papers whose title + abstract best match the question.
        score = cosine similarity (higher is more relevant, max 1.0)."""
        res = self.papers.query(query_texts=[question], n_results=min(k, self.papers.count()))
        return [
            {"id": pid, "title": meta["title"], "url": meta["url"], "score": round(1 - dist, 3)}
            for pid, meta, dist in zip(res["ids"][0], res["metadatas"][0], res["distances"][0])
        ]


if __name__ == "__main__":
    indexer = PaperIndexer()
    # Index any new papers (safe to re-run; only new ones are added)
    print(indexer.index_papers(), "new paper(s) indexed,", indexer.papers.count(), "total")
    # Ask a question
    for r in indexer.search("How can we reduce the cost of running LLM agents?"):
        print(r["score"], r["id"], r["title"], r["url"])
