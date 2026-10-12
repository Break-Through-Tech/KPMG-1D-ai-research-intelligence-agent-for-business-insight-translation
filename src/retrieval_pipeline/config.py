"""Data locations and settings for arXiv retrieval."""

from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RetrievalConfig:
    """Retrieval data locations resolved relative to the repository checkout."""
    repository_root: Path = REPOSITORY_ROOT
    downloaded_directory: Path = Path("data/downloaded")
    metadata_path: Path = Path("data/downloaded/metadata.csv")
    arxiv_query: str = "cat:cs.AI"      # Which arXiv papers to download 
    arxiv_delay_seconds: float = 3.0    #mandatory by api rules

    def resolve(self, path: Path) -> Path:
        """Resolve a configured repository-relative path to an absolute path."""
        return path if path.is_absolute() else self.repository_root / path
