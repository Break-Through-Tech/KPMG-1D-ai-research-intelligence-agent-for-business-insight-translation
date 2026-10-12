"""Data locations and settings for paper indexing and search."""

from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class IndexingConfig:
    """Indexing data locations resolved relative to the repository checkout."""

    repository_root: Path = REPOSITORY_ROOT
    metadata_path: Path = Path("data/downloaded/metadata.csv")
    chroma_directory: Path = Path("data/chroma")

    # Embedding model and the ChromaDB collection with one entry per paper
    embedding_model: str = "all-MiniLM-L6-v2"
    papers_collection: str = "papers"

    def resolve(self, path: Path) -> Path:
        """Resolve a configured repository-relative path to an absolute path."""

        return path if path.is_absolute() else self.repository_root / path
