"""Compare embedding models on a fixed paper-retrieval evaluation set.

Run from the repository root:
    python -m indexing_pipeline.embedding_benchmark

The benchmark uses separate Chroma directories for every model, so changing
models cannot silently reuse vectors produced by another model.
"""

import argparse
import csv
import json
import statistics
import time
from pathlib import Path

from indexing_pipeline.config import IndexingConfig
from indexing_pipeline.indexing import PaperIndexer


DEFAULT_MODELS = {
    "minilm": "all-MiniLM-L6-v2",
    "bge-small": "BAAI/bge-small-en-v1.5",
    "mpnet": "all-mpnet-base-v2",
}
DEFAULT_QUESTIONS = Path("data/evaluation/embedding_questions.json")
DEFAULT_OUTPUT = Path("data/evaluation/embedding_results.csv")


def load_questions(path: Path) -> list[dict]:
    """Load and validate the fixed evaluation questions."""

    questions = json.loads(path.read_text(encoding="utf-8"))
    if not questions:
        raise ValueError(f"No evaluation questions found in {path}")
    for question in questions:
        if not question.get("id") or not question.get("question"):
            raise ValueError("Each question needs a non-empty id and question")
        if not question.get("relevant_papers"):
            raise ValueError(f"Question {question['id']} has no relevant papers")
    return questions


def reciprocal_rank(results: list[dict], relevant_papers: set[str]) -> float:
    """Return the reciprocal rank of the first relevant retrieved paper."""

    for rank, result in enumerate(results, start=1):
        if result["paper_id"] in relevant_papers:
            return 1.0 / rank
    return 0.0


def evaluate_model(
    short_name: str,
    model_name: str,
    questions: list[dict],
    repository_root: Path,
) -> list[dict]:
    """Build one model index and return one metric row per question."""

    directory = Path("data/benchmark-chroma") / short_name
    config = IndexingConfig(
        repository_root=repository_root,
        embedding_model=model_name,
        chroma_directory=directory,
    )
    build_started = time.perf_counter()
    indexer = PaperIndexer(config)
    papers_added = indexer.index_papers()
    chunks_added = indexer.index_chunks()
    build_seconds = time.perf_counter() - build_started

    rows = []
    for item in questions:
        relevant_papers = set(item["relevant_papers"])
        # Warm the model and database before measuring query latency.
        indexer.search_two_stage(item["question"], n_papers=10, k=5)
        started = time.perf_counter()
        results = indexer.search_two_stage(item["question"], n_papers=10, k=5)
        latency_ms = (time.perf_counter() - started) * 1000
        retrieved_papers = [result["paper_id"] for result in results]
        hit = bool(relevant_papers.intersection(retrieved_papers))
        rows.append(
            {
                "model": short_name,
                "model_name": model_name,
                "question_id": item["id"],
                "recall_at_5": int(hit),
                "reciprocal_rank": reciprocal_rank(results, relevant_papers),
                "latency_ms": round(latency_ms, 2),
                "retrieved_papers": "|".join(retrieved_papers),
                "relevant_papers": "|".join(sorted(relevant_papers)),
                "papers_added": papers_added,
                "chunks_added": chunks_added,
                "build_seconds": round(build_seconds, 2),
            }
        )
    return rows


def write_results(rows: list[dict], output: Path) -> None:
    """Write detailed per-question results as CSV."""

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[dict]) -> None:
    """Print aggregate metrics while retaining per-question results in CSV."""

    print("\nModel comparison")
    print("model       Recall@5   MRR      latency p50 (ms)")
    for model in DEFAULT_MODELS:
        model_rows = [row for row in rows if row["model"] == model]
        if not model_rows:
            continue
        recalls = [row["recall_at_5"] for row in model_rows]
        mrrs = [row["reciprocal_rank"] for row in model_rows]
        latencies = [row["latency_ms"] for row in model_rows]
        print(
            f"{model:<11} {statistics.mean(recalls):.3f}      "
            f"{statistics.mean(mrrs):.3f}    {statistics.median(latencies):.2f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[2]
    questions = load_questions(repository_root / args.questions)
    rows = []
    for short_name, model_name in DEFAULT_MODELS.items():
        print(f"\n[{short_name}] {model_name}")
        rows.extend(evaluate_model(short_name, model_name, questions, repository_root))
    write_results(rows, repository_root / args.output)
    print_summary(rows)
    print(f"\nDetailed results: {repository_root / args.output}")


if __name__ == "__main__":
    main()
