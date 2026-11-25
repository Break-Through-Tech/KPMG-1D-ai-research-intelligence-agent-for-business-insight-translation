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
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from indexing_pipeline.config import IndexingConfig
from indexing_pipeline.indexing import PaperIndexer


@dataclass(frozen=True)
class BenchmarkModel:
    short_name: str
    model_name: str
    provider: str


LOCAL_MODELS = (
    BenchmarkModel("minilm", "all-MiniLM-L6-v2", "sentence-transformers"),
    BenchmarkModel("bge-small", "BAAI/bge-small-en-v1.5", "sentence-transformers"),
    BenchmarkModel("mpnet", "all-mpnet-base-v2", "sentence-transformers"),
    BenchmarkModel("bge-base", "BAAI/bge-base-en-v1.5", "sentence-transformers"),
    BenchmarkModel("bge-large", "BAAI/bge-large-en-v1.5", "sentence-transformers"),
    BenchmarkModel("e5-large", "intfloat/e5-large-v2", "sentence-transformers-e5"),
    BenchmarkModel("e5-base", "intfloat/e5-base-v2", "sentence-transformers-e5"),
    BenchmarkModel("gte-base", "thenlper/gte-base", "sentence-transformers"),
)
DEFAULT_QUESTION_FILES = (
    Path("evaluation/benchmark_questions_2.json"),
    Path("evaluation/prompts_labeled.json"),
)
DEFAULT_COMPARISON_OUTPUT = Path("data/evaluation/embedding_comparison_labeled.csv")
DEFAULT_DETAILS_OUTPUT = Path("data/evaluation/embedding_results_labeled.csv")


def load_questions(paths: list[Path]) -> tuple[list[dict], int]:
    """Load answerable, labeled questions and count unanswerable items skipped."""

    questions = []
    skipped = 0
    seen_ids = set()
    for path in paths:
        items = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(items, list) or not items:
            raise ValueError(f"No evaluation questions found in {path}")
        for item in items:
            question_id = item.get("id")
            if not question_id or not item.get("question"):
                raise ValueError(f"Each question in {path} needs a non-empty id and question")
            if question_id in seen_ids:
                raise ValueError(f"Duplicate question id: {question_id}")
            seen_ids.add(question_id)
            relevant_papers = item.get("relevant_papers", [])
            if not relevant_papers and item.get("answerable") is False:
                skipped += 1
                continue
            if not isinstance(relevant_papers, list) or not relevant_papers:
                raise ValueError(f"Question {question_id} needs labeled relevant papers")
            questions.append({**item, "question_set": path.stem})
    if not questions:
        raise ValueError("No answerable, labeled evaluation questions found")
    return questions, skipped


def reciprocal_rank(results: list[dict], relevant_papers: set[str]) -> float:
    """Return the reciprocal rank of the first relevant retrieved paper."""

    for rank, result in enumerate(results, start=1):
        if result["paper_id"] in relevant_papers:
            return 1.0 / rank
    return 0.0


def ranked_unique_papers(results: list[dict]) -> list[str]:
    """Return unique paper IDs in first-seen retrieval order."""

    return list(dict.fromkeys(result["paper_id"] for result in results))


def evaluate_model(
    short_name: str,
    model_name: str,
    provider: str,
    questions: list[dict],
    repository_root: Path,
    on_row: Callable[[dict], None] | None = None,
) -> list[dict]:
    """Build one model index and return one metric row per question."""

    directory = Path("data/benchmark-chroma") / short_name
    config = IndexingConfig(
        repository_root=repository_root,
        embedding_model=model_name,
        embedding_provider=provider,
        chroma_directory=directory,
    )
    build_started = time.perf_counter()
    indexer = PaperIndexer(config)
    print("  Indexing paper abstracts...", flush=True)
    papers_added = indexer.index_papers()

    def report_index_progress(completed, total):
        print(f"  Indexing passage embeddings: {completed}/{total}", flush=True)

    chunks_added = indexer.index_chunks(
        batch_size=128,
        progress_callback=report_index_progress,
    )
    build_seconds = time.perf_counter() - build_started
    print(f"  Index ready in {build_seconds:.1f}s; evaluating {len(questions)} question(s).",
          flush=True)

    rows = []
    question_results = indexer.iter_search_two_stage(
        (item["question"] for item in questions),
        n_papers=10,
        k=100,
    )
    for question_number, (item, (results, latency_ms)) in enumerate(
        zip(questions, question_results), start=1
    ):
        relevant_papers = set(item["relevant_papers"])
        retrieved_papers = ranked_unique_papers(results)[:5]
        row = {
            "model": short_name,
            "model_name": model_name,
            "question_set": item["question_set"],
            "question_id": item["id"],
            "recall_at_5": round(
                len(relevant_papers.intersection(retrieved_papers)) / len(relevant_papers), 4
            ),
            "reciprocal_rank": reciprocal_rank(
                [{"paper_id": paper_id} for paper_id in retrieved_papers], relevant_papers
            ),
            "latency_ms": round(latency_ms, 2),
            "retrieved_papers": "|".join(retrieved_papers),
            "relevant_papers": "|".join(sorted(relevant_papers)),
            "papers_added": papers_added,
            "chunks_added": chunks_added,
            "build_seconds": round(build_seconds, 2),
        }
        rows.append(row)
        if on_row is not None:
            on_row(row)
        print(
            f"  Question {question_number}/{len(questions)} ({item['id']}): "
            f"Recall@5={row['recall_at_5']:.3f}, MRR={row['reciprocal_rank']:.3f}, "
            f"latency={row['latency_ms']:.2f}ms",
            flush=True,
        )
    return rows


def write_results(rows: list[dict], output: Path) -> None:
    """Atomically write detailed or aggregate results as CSV."""

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            newline="",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = Path(file.name)
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        temporary_path.replace(output)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def load_existing_results(
    path: Path, questions: list[dict], models: tuple[BenchmarkModel, ...]
) -> list[dict]:
    """Load compatible per-question rows to resume an interrupted benchmark."""

    if not path.exists():
        return []
    questions_by_id = {question["id"]: question for question in questions}
    models_by_name = {model.short_name: model for model in models}
    numeric_fields = ("recall_at_5", "reciprocal_rank", "latency_ms", "build_seconds")
    integer_fields = ("papers_added", "chunks_added")
    rows_by_key = {}
    with path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            model = models_by_name.get(row.get("model"))
            question = questions_by_id.get(row.get("question_id"))
            if model is None or question is None:
                continue
            expected_relevant = "|".join(sorted(question["relevant_papers"]))
            if (
                row.get("model_name") != model.model_name
                or row.get("question_set") != question["question_set"]
                or row.get("relevant_papers") != expected_relevant
            ):
                raise ValueError(
                    f"Existing result for {model.short_name}/{question['id']} "
                    "does not match the current benchmark inputs"
                )
            for field in numeric_fields:
                row[field] = float(row[field])
            for field in integer_fields:
                row[field] = int(row[field])
            rows_by_key[(model.short_name, question["id"])] = row
    return list(rows_by_key.values())


def aggregate_results(rows: list[dict]) -> list[dict]:
    """Create one decision-oriented comparison row per model."""

    aggregated = []
    models = {model.short_name: model for model in LOCAL_MODELS}
    for model_name in dict.fromkeys(row["model"] for row in rows):
        model = models[model_name]
        model_rows = [row for row in rows if row["model"] == model_name]
        if not model_rows:
            continue
        aggregated.append(
            {
                "model": model.short_name,
                "model_name": model.model_name,
                "provider": model.provider,
                "questions": len(model_rows),
                "question_sets": "|".join(sorted({row["question_set"] for row in model_rows})),
                "recall_at_5": round(statistics.mean(row["recall_at_5"] for row in model_rows), 4),
                "mrr": round(statistics.mean(row["reciprocal_rank"] for row in model_rows), 4),
                "latency_p50_ms": round(statistics.median(row["latency_ms"] for row in model_rows), 2),
                "latency_mean_ms": round(statistics.mean(row["latency_ms"] for row in model_rows), 2),
                "build_seconds": model_rows[0]["build_seconds"],
                "papers_added": model_rows[0]["papers_added"],
                "chunks_added": model_rows[0]["chunks_added"],
            }
        )
    return aggregated


def print_summary(rows: list[dict]) -> None:
    """Print aggregate metrics while retaining per-question results in CSV."""

    print("\nModel comparison")
    print("model       Recall@5   MRR      latency p50 (ms)")
    models = {model.short_name: model for model in LOCAL_MODELS}
    for model_name in dict.fromkeys(row["model"] for row in rows):
        model = models[model_name]
        model_rows = [row for row in rows if row["model"] == model.short_name]
        if not model_rows:
            continue
        recalls = [row["recall_at_5"] for row in model_rows]
        mrrs = [row["reciprocal_rank"] for row in model_rows]
        latencies = [row["latency_ms"] for row in model_rows]
        print(
            f"{model.short_name:<14} {statistics.mean(recalls):.3f}      "
            f"{statistics.mean(mrrs):.3f}    {statistics.median(latencies):.2f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--questions",
        type=Path,
        action="append",
        help="Evaluation JSON file; repeat to combine datasets (defaults to both labeled sets)",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_COMPARISON_OUTPUT,
                        help="Aggregate one-row-per-model comparison CSV")
    parser.add_argument("--details-output", type=Path, default=DEFAULT_DETAILS_OUTPUT,
                        help="Per-question results CSV")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse compatible completed question rows from the details CSV",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        choices=[model.short_name for model in LOCAL_MODELS],
        help="Local model short names to run (defaults to all; useful for offline cached models)",
    )
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[2]
    question_files = args.questions or list(DEFAULT_QUESTION_FILES)
    questions, skipped = load_questions([repository_root / path for path in question_files])
    if skipped:
        print(f"Skipping {skipped} unanswerable question(s) without relevant-paper labels.")
    requested_models = set(args.models) if args.models else None
    models = tuple(
        model for model in LOCAL_MODELS
        if requested_models is None or model.short_name in requested_models
    )
    details_output = repository_root / args.details_output
    comparison_output = repository_root / args.output
    rows = load_existing_results(details_output, questions, models) if args.resume else []

    def save_progress(_row=None):
        if rows:
            write_results(rows, details_output)
            write_results(aggregate_results(rows), comparison_output)

    if rows:
        print(f"Resuming with {len(rows)} saved question result(s).", flush=True)
        save_progress()

    for model in models:
        model_question_ids = {
            row["question_id"] for row in rows if row["model"] == model.short_name
        }
        pending_questions = [
            question for question in questions if question["id"] not in model_question_ids
        ]
        if not pending_questions:
            print(f"\n[{model.short_name}] already complete; skipping.", flush=True)
            continue
        print(
            f"\n[{model.short_name}] {model.model_name} "
            f"({len(model_question_ids)}/{len(questions)} questions saved)",
            flush=True,
        )
        def record_row(row: dict) -> None:
            rows.append(row)
            save_progress()

        evaluate_model(
            model.short_name,
            model.model_name,
            model.provider,
            pending_questions,
            repository_root,
            on_row=record_row,
        )
    if rows:
        save_progress()
    print_summary(rows)
    print(f"\nComparison results: {comparison_output}")
    print(f"Detailed results: {details_output}")


if __name__ == "__main__":
    main()
