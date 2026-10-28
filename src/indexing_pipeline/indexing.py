"""Two-stage search over the selected, validated research passage generation."""

import json

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from indexing_pipeline.config import IndexingConfig
from research_pipeline.chunking import sha256_bytes
from research_pipeline.datasets import load_active_dataset
from research_pipeline.models import PaperMetadata


class PaperIndexer:
    """Keep paper and passage vectors aligned with one published generation."""

    def __init__(self, config=IndexingConfig(), embedding_function=None):
        self.config = config
        self.manifest_path = config.resolve(config.manifest_path)
        self.run_root = config.resolve(config.run_root)
        self.active_pointer = config.resolve(config.active_pointer)
        self.chroma_dir = config.resolve(config.chroma_directory)
        self._source()
        self.embed_fn = (embedding_function if embedding_function is not None else
                         SentenceTransformerEmbeddingFunction(model_name=config.embedding_model))
        self.db = chromadb.PersistentClient(path=str(self.chroma_dir))
        self.papers = self.db.get_or_create_collection(
            config.papers_collection, embedding_function=self.embed_fn, configuration={"hnsw": {"space": "cosine"}}
        )
        self.chunks = self.db.get_or_create_collection(
            config.chunks_collection, embedding_function=self.embed_fn, configuration={"hnsw": {"space": "cosine"}}
        )

    def _source(self):
        """Validate the active data and its search metadata before any index mutation."""
        dataset = load_active_dataset(self.run_root, self.active_pointer)
        manifest_bytes = self.manifest_path.read_bytes()
        if sha256_bytes(manifest_bytes) != dataset.manifest["provenance"]["source_hashes"]["manifest"]:
            raise ValueError("paper manifest differs from active passage generation")
        rows = json.loads(manifest_bytes)
        if not isinstance(rows, list):
            raise ValueError("paper manifest must be a list")
        by_id = {row["paper_id"]: row for row in rows}
        if len(by_id) != len(rows) or sorted((PaperMetadata.from_dict(row) for row in rows),
                                              key=lambda record: record.paper_id) != sorted(
                dataset.papers, key=lambda record: record.paper_id):
            raise ValueError("paper manifest metadata differs from active passage generation")
        included = set(dataset.manifest["included_paper_ids"])
        for paper_id in included:
            row = by_id[paper_id]
            if not isinstance(row.get("abstract"), str) or not row["abstract"].strip():
                raise ValueError(f"missing abstract for indexed paper: {paper_id}")
            if not isinstance(row.get("url"), str) or not row["url"].strip():
                raise ValueError(f"missing URL for indexed paper: {paper_id}")
        return dataset, by_id

    @staticmethod
    def _reconcile(collection, desired):
        """Upsert changed records and delete vectors absent from the selected corpus."""
        stored = collection.get(include=["documents", "metadatas"])
        existing = {identifier: (document, metadata) for identifier, document, metadata in zip(
            stored["ids"], stored["documents"], stored["metadatas"])}
        changed = [(identifier, document, metadata) for identifier, (document, metadata) in desired.items()
                   if existing.get(identifier) != (document, metadata)]
        for start in range(0, len(changed), 1000):
            batch = changed[start:start + 1000]
            collection.upsert(ids=[row[0] for row in batch], documents=[row[1] for row in batch],
                              metadatas=[row[2] for row in batch])
        stale = sorted(set(existing) - set(desired))
        for start in range(0, len(stale), 1000):
            collection.delete(ids=stale[start:start + 1000])
        return len(changed)

    def index_papers(self):
        """Synchronize abstract vectors for the active corpus; return changed count."""
        dataset, by_id = self._source()
        generation = dataset.directory.name
        desired = {}
        for paper_id in dataset.manifest["included_paper_ids"]:
            row = by_id[paper_id]
            desired[paper_id] = (f"{row['title']}. {row['abstract']}",
                                 {"paper_id": paper_id, "title": row["title"], "url": row["url"],
                                  "published": row["published"], "generation": generation})
        return self._reconcile(self.papers, desired)

    def index_chunks(self):
        """Synchronize exact published passages and source offsets; return changed count."""
        dataset, _ = self._source()
        generation = dataset.directory.name
        desired = {chunk.chunk_id: (chunk.text, {
            "paper_id": chunk.paper_id, "page_number": chunk.page_number,
            "start_character": chunk.start_character, "end_character": chunk.end_character,
            "page_text_sha256": chunk.page_text_sha256,
            "chunking_profile_sha256": chunk.chunking_profile_sha256,
            "title": chunk.title, "pdf_url": chunk.pdf_url, "generation": generation,
        }) for chunk in dataset.chunks}
        return self._reconcile(self.chunks, desired)

    @staticmethod
    def _require_ids(collection, expected, generation, name):
        actual = set(collection.get(where={"generation": generation}, include=[])["ids"])
        if actual != set(expected):
            raise RuntimeError(f"{name} index is not synchronized with the active generation")

    def _search_papers(self, question, k, dataset):
        generation = dataset.directory.name
        self._require_ids(self.papers, dataset.manifest["included_paper_ids"], generation, "paper")
        count = len(dataset.manifest["included_paper_ids"])
        if not count:
            return []
        result = self.papers.query(query_texts=[question], n_results=min(k, count),
                                   where={"generation": generation}, include=["metadatas", "distances"])
        return [{"id": identifier, "title": metadata["title"], "url": metadata["url"],
                 "score": round(1 - distance, 3)} for identifier, metadata, distance in zip(
                     result["ids"][0], result["metadatas"][0], result["distances"][0])]

    def search(self, question, k=5):
        """Return matching papers from the active generation only."""
        dataset, _ = self._source()
        return self._search_papers(question, k, dataset)

    def _search_chunks(self, question, paper_ids, k, dataset):
        generation = dataset.directory.name
        self._require_ids(self.chunks, [chunk.chunk_id for chunk in dataset.chunks], generation, "passage")
        allowed = set(dataset.manifest["included_paper_ids"])
        paper_ids = sorted(set(paper_ids) & allowed)
        if not paper_ids or not dataset.chunks:
            return []
        result = self.chunks.query(query_texts=[question], n_results=min(k, len(dataset.chunks)),
                                   where={"$and": [{"generation": generation},
                                                   {"paper_id": {"$in": paper_ids}}]},
                                   include=["documents", "metadatas", "distances"])
        return [{"chunk_id": identifier, "paper_id": metadata["paper_id"],
                 "page_number": metadata["page_number"],
                 "start_character": metadata["start_character"],
                 "end_character": metadata["end_character"],
                 "pdf_url": metadata["pdf_url"],
                 "page_text_sha256": metadata["page_text_sha256"], "text": document,
                 "score": round(1 - distance, 3)} for identifier, metadata, document, distance in zip(
                     result["ids"][0], result["metadatas"][0], result["documents"][0],
                     result["distances"][0])]

    def search_chunks(self, question, paper_ids, k=5):
        """Return only active passages from the candidate papers."""
        dataset, _ = self._source()
        return self._search_chunks(question, paper_ids, k, dataset)

    def search_two_stage(self, question, n_papers=10, k=5):
        """Select papers then retrieve their active, citation-bearing passages."""
        dataset, _ = self._source()
        candidates = self._search_papers(question, n_papers, dataset)
        return self._search_chunks(question, [paper["id"] for paper in candidates], k, dataset)


if __name__ == "__main__":
    indexer = PaperIndexer()
    print(indexer.index_papers(), "paper vector(s) updated")
    print(indexer.index_chunks(), "passage vector(s) updated")
    for passage in indexer.search_two_stage("How can we reduce the cost of running LLM agents?"):
        print(passage["score"], passage["paper_id"], "page", passage["page_number"],
              "|", " ".join(passage["text"].split())[:150])
