"""Data locations and settings for paper indexing and search."""

from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class IndexingConfig:
    """Indexing data locations resolved relative to the repository checkout."""

    repository_root: Path = REPOSITORY_ROOT
    manifest_path: Path = Path("data/manifest/papers.json")
    run_root: Path = Path("data/processed/runs")
    active_pointer: Path = Path("data/processed/active_run.json")
    chroma_directory: Path = Path("data/chroma")

    # Embedding model and the ChromaDB collection with one entry per paper
    embedding_model: str = "all-MiniLM-L6-v2"
    papers_collection: str = "papers"

    # ChromaDB collection with one entry per validated passage
    chunks_collection: str = "chunks"

    def resolve(self, path: Path) -> Path:
        """Resolve a configured repository-relative path to an absolute path."""

        return path if path.is_absolute() else self.repository_root / path
