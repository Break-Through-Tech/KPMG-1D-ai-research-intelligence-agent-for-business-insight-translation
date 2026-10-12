"""Data locations and settings for the retrieval and indexing notebooks."""

from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class NotebookConfig:
    """Notebook data locations resolved relative to the repository checkout."""

    repository_root: Path = REPOSITORY_ROOT
    downloaded_directory: Path = Path("data/downloaded")
    metadata_path: Path = Path("data/downloaded/metadata.csv")
    chroma_directory: Path = Path("data/chroma")

    # Which arXiv papers to download and the pause between API calls
    arxiv_query: str = "cat:cs.AI"
    arxiv_delay_seconds: float = 3.0 #mandatory by api rules 

    # Embedding model and the ChromaDB collection with one entry per paper
    embedding_model: str = "all-MiniLM-L6-v2"
    papers_collection: str = "papers"

    def resolve(self, path: Path) -> Path:
        """Resolve a configured repository-relative path to an absolute path."""

        return path if path.is_absolute() else self.repository_root / path
