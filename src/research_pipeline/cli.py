"""Local preparation CLI: run, chunk, inspect, and read-only corpus coverage."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

from research_pipeline.chunking import ChunkingConfig
from research_pipeline.config import PipelineConfig, REPOSITORY_ROOT
from research_pipeline.datasets import load_active_dataset
from research_pipeline.handoff import compare_corpus_ids
from research_pipeline.outcomes import exit_code_for_outcome
from research_pipeline.pipeline import run_chunking, run_pipeline


def build_parser() -> argparse.ArgumentParser:
    """Expose explicit local paths and profile settings; no implicit collection."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "chunk", "inspect", "coverage"):
        command = commands.add_parser(name)
        command.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
        command.add_argument("--run-root", type=Path, default=Path("data/processed/runs"))
        command.add_argument("--active-pointer", type=Path, default=Path("data/processed/active_run.json"))
        if name in ("run", "chunk"):
            command.add_argument("--manifest", type=Path, default=Path("data/manifest/papers.json"))
            command.add_argument("--allow-partial", action="store_true")
            command.add_argument("--profile", choices=("boundary_characters", "fixed_characters", "tokenizer"),
                                 default="boundary_characters")
            command.add_argument("--chunk-size", type=int, default=1800)
            command.add_argument("--chunk-overlap", type=int, default=200)
            command.add_argument("--token-budget", type=int, default=200)
            command.add_argument("--token-overlap", type=int, default=40)
            command.add_argument("--max-input-tokens", type=int, default=256)
            command.add_argument("--tokenizer-file", type=Path)
            command.add_argument("--tokenizer-model-id")
            command.add_argument("--tokenizer-revision")
        if name == "chunk":
            command.add_argument("--pages", type=Path, default=Path("data/processed/pages.jsonl"))
            command.add_argument("--catalog", type=Path)
        if name == "coverage":
            command.add_argument("--metadata-csv", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Print one JSON outcome; processing codes are success 0, partial 2, failure 3."""
    args = build_parser().parse_args(argv)
    try:
        config = PipelineConfig(repository_root=args.repository_root.resolve())
        if args.command in ("run", "chunk"):
            config = replace(config, manifest_path=args.manifest)
            settings = ChunkingConfig(profile=args.profile, size=args.chunk_size,
                                      overlap=args.chunk_overlap, token_budget=args.token_budget,
                                      token_overlap=args.token_overlap, max_input_tokens=args.max_input_tokens)
            tokenizer = None
            if args.profile == "tokenizer":
                if not args.tokenizer_file:
                    raise ValueError("tokenizer profile requires --tokenizer-file and declared identity")
                from research_pipeline.tokenization import LocalTokenizer
                tokenizer = LocalTokenizer.from_file(config.resolve(args.tokenizer_file),
                                                     args.tokenizer_model_id, args.tokenizer_revision)
            elif args.tokenizer_file or args.tokenizer_model_id or args.tokenizer_revision:
                raise ValueError("tokenizer options require --profile tokenizer")
            options = {"run_root": args.run_root, "pointer_path": args.active_pointer,
                       "allow_partial": args.allow_partial, "tokenizer": tokenizer}
            if args.command == "run":
                result = run_pipeline(config, settings, **options)
            else:
                config = replace(config, extracted_pages_path=args.pages)
                result = run_chunking(config, settings, catalog_path=args.catalog, **options)
        else:
            dataset = load_active_dataset(config.resolve(args.run_root), config.resolve(args.active_pointer))
            if args.command == "inspect":
                result = {"outcome": "success", "dataset_outcome": dataset.manifest["outcome"],
                          "generation": dataset.directory.name, "papers": len(dataset.papers),
                          "pages": len(dataset.pages), "chunks": len(dataset.chunks),
                          "included_paper_ids": dataset.manifest["included_paper_ids"],
                          "excluded_paper_ids": dataset.manifest["excluded_paper_ids"]}
            else:
                result = {"outcome": "success", **compare_corpus_ids(
                    dataset.manifest["included_paper_ids"], config.resolve(args.metadata_csv))}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return exit_code_for_outcome(result["outcome"])
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"outcome": "failure", "artifacts_published": False, "error": str(error)}, indent=2))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
