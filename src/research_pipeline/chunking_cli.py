"""Independent chunking command using existing page JSONL; no PDF parsing."""

import sys

from research_pipeline.cli import main as pipeline_main


def main(argv: list[str] | None = None) -> int:
    """Run the chunk subcommand with the same explicit paths and outcome policy."""
    return pipeline_main(["chunk", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    raise SystemExit(main())
