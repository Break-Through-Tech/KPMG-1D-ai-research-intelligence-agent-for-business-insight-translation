"""Stage 1 command-line interface for paper ingestion and arXiv collection."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

from research_pipeline.config import PipelineConfig
from research_pipeline.ingestion import ARXIV_API_URL, build_paper_catalog, collect_arxiv_papers
from research_pipeline.outcomes import FAILURE, SUCCESS, exit_code_for_outcome
from research_pipeline.publication import publish_staged_outputs, staged_output_config


def run_ingest(config: PipelineConfig) -> tuple[object, bool]:
    """Build a staged catalog and publish it only for a complete local corpus."""

    fields = ("paper_catalog_path",)
    with staged_output_config(config, fields) as staged_config:
        report = build_paper_catalog(staged_config)
        published = report.outcome == SUCCESS
        if published:
            publish_staged_outputs(staged_config, config, fields)
        return report, published


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", help="repository-relative paper manifest path")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("ingest", help="validate the manifest and build the paper catalog")
    collect_parser = subparsers.add_parser("collect", help="collect explicit versioned arXiv IDs")
    collect_parser.add_argument("--arxiv-id", action="append", required=True, dest="arxiv_ids")
    collect_parser.add_argument("--download-pdf", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = PipelineConfig()
    if args.manifest:
        config = replace(config, manifest_path=Path(args.manifest))
    try:
        if args.command == "ingest":
            report, published = run_ingest(config)
            payload = {**report.to_dict(), "artifacts_published": published}
        else:
            print(f"Live source: {ARXIV_API_URL} and arXiv PDF endpoints")
            print(f"Explicit paper count: {len(args.arxiv_ids)}")
            report = collect_arxiv_papers(args.arxiv_ids, config, args.download_pdf)
            payload = report.to_dict()
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return exit_code_for_outcome(report.outcome)
    except (OSError, ValueError) as error:
        print(json.dumps({"outcome": FAILURE, "error": str(error)}, indent=2))
        return exit_code_for_outcome(FAILURE)


if __name__ == "__main__":
    raise SystemExit(main())
