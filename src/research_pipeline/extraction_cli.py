"""Stage 2 command-line interface for page-level PDF extraction."""

from __future__ import annotations

import argparse
import json

from research_pipeline.config import PipelineConfig
from research_pipeline.extraction import ExtractionReport, extract_manifest_pages
from research_pipeline.outcomes import FAILURE, PARTIAL_FAILURE, SUCCESS, exit_code_for_outcome
from research_pipeline.publication import publish_staged_outputs, staged_output_config


def run_extract(
    config: PipelineConfig,
    allow_partial: bool = False,
) -> tuple[ExtractionReport, bool]:
    """Extract into staging and return the report and publication flag.

    A complete run replaces the configured page JSONL. Incomplete usable
    results replace it only with allow_partial=True; total failures never
    publish. Validation/filesystem exceptions propagate and leave the previous
    output untouched until publication. Temporary files are cleaned on exit.
    """

    fields = ("extracted_pages_path",)
    with staged_output_config(config, fields) as staged_config:
        report = extract_manifest_pages(staged_config)
        published = report.outcome == SUCCESS or (
            report.outcome == PARTIAL_FAILURE and allow_partial
        )
        if published:
            publish_staged_outputs(staged_config, config, fields)
        return report, published


def build_parser() -> argparse.ArgumentParser:
    """Build the standalone extraction CLI without later-stage dependencies."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Publish incomplete usable page output; still return exit code 2.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Print an extraction report and return outcome exit code 0, 2, or 3."""

    args = build_parser().parse_args(argv)
    try:
        report, published = run_extract(PipelineConfig(), allow_partial=args.allow_partial)
        print(json.dumps({**report.to_dict(), "artifacts_published": published}, indent=2))
        return exit_code_for_outcome(report.outcome)
    except (OSError, ValueError) as error:
        print(json.dumps({"outcome": FAILURE, "error": str(error)}, indent=2))
        return exit_code_for_outcome(FAILURE)


if __name__ == "__main__":
    raise SystemExit(main())
