"""Temporary output staging and validated artifact publication helpers."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import tempfile
from typing import Iterator

from research_pipeline.config import PipelineConfig


@contextmanager
def staged_output_config(
    config: PipelineConfig,
    path_fields: tuple[str, ...],
) -> Iterator[PipelineConfig]:
    """Yield a config whose selected outputs live in a temporary data directory."""

    staging_parent = config.repository_root / "data"
    staging_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pipeline-staging-", dir=staging_parent) as directory:
        staging_directory = Path(directory)
        replacements = {
            field_name: staging_directory / Path(getattr(config, field_name)).name
            for field_name in path_fields
        }
        yield replace(config, **replacements)


def publish_staged_outputs(
    staged_config: PipelineConfig,
    destination_config: PipelineConfig,
    path_fields: tuple[str, ...],
) -> None:
    """Replace destinations only after every expected staged artifact exists."""

    source_and_destination = [
        (
            staged_config.resolve(Path(getattr(staged_config, field_name))),
            destination_config.resolve(Path(getattr(destination_config, field_name))),
        )
        for field_name in path_fields
    ]
    missing = [str(source) for source, _ in source_and_destination if not source.is_file()]
    if missing:
        raise ValueError(f"cannot publish missing staged artifacts: {', '.join(missing)}")

    for source, destination in source_and_destination:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
