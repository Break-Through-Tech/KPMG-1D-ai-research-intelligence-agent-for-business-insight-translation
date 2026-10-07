"""Read-only corpus identity comparison for a future two-stage retrieval handoff."""

import csv
from pathlib import Path

from research_pipeline.models import ARXIV_ID_PATTERN


def compare_corpus_ids(passage_ids: list[str], metadata_csv: Path) -> dict[str, list[str]]:
    """Compare exact versioned IDs without fetching papers or modifying either input.

    Raises ValueError for missing/duplicate columns, duplicate IDs, or noncanonical
    identities. Non-overlapping datasets cannot support candidate-paper filtering.
    """
    passage_set = set(passage_ids)
    if len(passage_set) != len(passage_ids) or any(not isinstance(item, str) or not
            ARXIV_ID_PATTERN.fullmatch(item) for item in passage_ids):
        raise ValueError("passage IDs must be canonical and unique")
    with Path(metadata_csv).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or reader.fieldnames.count("id") != 1 or len(
                reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("metadata CSV must have an unambiguous id column")
        metadata_ids = []
        for row in reader:
            paper_id = row.get("id")
            if not isinstance(paper_id, str) or not ARXIV_ID_PATTERN.fullmatch(paper_id):
                raise ValueError("metadata CSV contains a noncanonical versioned paper ID")
            if paper_id in metadata_ids:
                raise ValueError("metadata CSV contains duplicate paper IDs")
            metadata_ids.append(paper_id)
    metadata_set = set(metadata_ids)
    return {"shared_ids": sorted(passage_set & metadata_set),
            "passages_only_ids": sorted(passage_set - metadata_set),
            "metadata_only_ids": sorted(metadata_set - passage_set)}
