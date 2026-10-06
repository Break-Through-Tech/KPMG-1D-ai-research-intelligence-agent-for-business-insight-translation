"""Repository paths for reproducible paper ingestion."""

from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class PipelineConfig:
    """Ingestion locations resolved relative to the repository checkout."""

    repository_root: Path = REPOSITORY_ROOT
    manifest_path: Path = Path("data/manifest/papers.json")
    downloaded_pdf_directory: Path = Path("data/raw/pdfs")
    paper_catalog_path: Path = Path("data/processed/papers.jsonl")

    def resolve(self, path: Path) -> Path:
        """Resolve a configured repository-relative path to an absolute path."""

        return path if path.is_absolute() else self.repository_root / path
