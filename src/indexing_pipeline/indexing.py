"""Two-stage paper search

Stage 1: embeds each paper's title + abstract from data/manifest/papers.json into the ChromaDB collection
"papers" (saved in data/chroma/), then searches it with a natural-language question.
Stage 2: cuts each page in data/manifest/pages.jsonl into chunks, embeds them into the collection "chunks",
then searches only the chunks of the papers found in stage 1.

Run retrieval_pipeline/retrieval.py first to download papers and extract their pages.
"""

import json
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from indexing_pipeline.config import IndexingConfig


class PaperIndexer:
    """Indexes papers (title + abstract) and chunks of their page text in ChromaDB and searches them."""
    def __init__(self, config=IndexingConfig()):
        # Input paper list + page text (from retrieval.py) and where the vector database is saved (set in config.py)
        self.config = config
        self.manifest_path = config.resolve(config.manifest_path)
        self.pages_path = config.resolve(config.pages_path)
        self.chroma_dir = config.resolve(config.chroma_directory)

        # Embedding model: turns text into 384 numbers that represent its meaning, fast and lightweight
        self.embed_fn = SentenceTransformerEmbeddingFunction(model_name=config.embedding_model)

        # Vector database on disk; "papers" = one entry per paper, compared by cosine similarity
        self.db = chromadb.PersistentClient(path=str(self.chroma_dir))
        self.papers = self.db.get_or_create_collection(
            config.papers_collection, embedding_function=self.embed_fn, configuration={"hnsw": {"space": "cosine"}}
        )
        # "chunks" = one entry per chunk of page text, each tagged with its paper id and page number
        self.chunks = self.db.get_or_create_collection(
            config.chunks_collection, embedding_function=self.embed_fn, configuration={"hnsw": {"space": "cosine"}}
        )

    def index_papers(self):
        """Add every paper in papers.json that isn't in the collection yet.
        Returns the number of papers added (0 if everything was already indexed)."""
        with open(self.manifest_path, encoding="utf-8") as f:
            rows = json.load(f)
        existing = set(self.papers.get(ids=[r["paper_id"] for r in rows])["ids"]) if rows else set()
        new_rows = [r for r in rows if r["paper_id"] not in existing]
        if new_rows:
            self.papers.add(
                ids=[r["paper_id"] for r in new_rows],
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

    def index_chunks(self):
        """Cut every page in pages.jsonl into chunks and add the ones that aren't in the collection yet.
        Returns the number of chunks added (0 if everything was already indexed)."""
        with open(self.pages_path, encoding="utf-8") as f:
            pages = [json.loads(line) for line in f if line.strip()]
        size = self.config.chunk_size
        rows = [
            {"id": f"{p['paper_id']}_p{p['page_number']}_{start // size}", "text": p["text"][start:start + size],
             "paper_id": p["paper_id"], "page_number": p["page_number"]}
            for p in pages for start in range(0, len(p["text"]), size)
        ]
        existing = set(self.chunks.get(include=[])["ids"])
        new_rows = [r for r in rows if r["id"] not in existing and r["text"].strip()]
        for start in range(0, len(new_rows), 1000):  # ChromaDB limits how many entries one add() can take
            batch = new_rows[start:start + 1000]
            self.chunks.add(
                ids=[r["id"] for r in batch],
                documents=[r["text"] for r in batch],  # the text that gets embedded
                metadatas=[{"paper_id": r["paper_id"], "page_number": r["page_number"]} for r in batch],
            )
        return len(new_rows)

    def search_chunks(self, question, paper_ids, k=5):
        """Return the k chunks that best match the question, only from the given papers.
        score = cosine similarity (higher is more relevant, max 1.0)."""
        if not paper_ids or self.chunks.count() == 0:
            return []
        res = self.chunks.query(
            query_texts=[question], n_results=min(k, self.chunks.count()), where={"paper_id": {"$in": paper_ids}}
        )
        return [
            {"paper_id": meta["paper_id"], "page_number": meta["page_number"], "text": text, "score": round(1 - dist, 3)}
            for meta, text, dist in zip(res["metadatas"][0], res["documents"][0], res["distances"][0])
        ]

    def search_two_stage(self, question, n_papers=10, k=5):
        """Stage 1 finds the n_papers best papers; stage 2 returns the k best chunks from only those papers."""
        top_papers = self.search(question, k=n_papers)
        return self.search_chunks(question, [p["id"] for p in top_papers], k)


if __name__ == "__main__":
    indexer = PaperIndexer()
    # Index any new papers and chunks (safe to re-run; only new ones are added)
    print(indexer.index_papers(), "new paper(s) indexed,", indexer.papers.count(), "total")
    print(indexer.index_chunks(), "new chunk(s) indexed,", indexer.chunks.count(), "total")
    # Ask a question: stage 1 (papers)
    question = "How can we reduce the cost of running LLM agents?"
    for r in indexer.search(question):
        print(r["score"], r["id"], r["title"], r["url"])
    # Ask the same question: stage 2 (passages from the top papers)
    for r in indexer.search_two_stage(question):
        print(r["score"], r["paper_id"], "page", r["page_number"], "|", " ".join(r["text"].split())[:150])
