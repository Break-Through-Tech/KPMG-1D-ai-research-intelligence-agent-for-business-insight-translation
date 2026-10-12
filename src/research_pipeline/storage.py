"""Small JSON and JSONL helpers with atomic writes and schema validation hooks."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any, Callable, Iterable, TypeVar


RecordType = TypeVar("RecordType")


def read_json(path: Path) -> Any:
    """Load UTF-8 JSON, allowing decoding and filesystem errors to surface."""

    with path.open(encoding="utf-8") as input_file:
        return json.load(input_file)


def write_bytes(path: Path, value: bytes) -> None:
    """Publish complete binary content using a temporary sibling and replacement.

    Args:
        path: Final artifact location; its parent is created if necessary.
        value: Complete downloaded bytes to store, not a streamed response.

    Raises:
        OSError: Writing, closing, or replacement fails. The previous destination
            remains unchanged and any temporary file is removed when possible.

    Atomic replacement avoids publishing incomplete writes; it does not validate
    PDF contents or guarantee crash durability across a power failure.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as output_file:
            temporary_path = Path(output_file.name)
            bytes_written = output_file.write(value)
            if bytes_written != len(value):
                raise OSError("incomplete binary artifact write")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def write_json(path: Path, value: Any) -> None:
    """Atomically write human-readable UTF-8 JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as output_file:
            temporary_path = Path(output_file.name)
            json.dump(value, output_file, ensure_ascii=False, indent=2)
            output_file.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> int:
    """Atomically write records as one compact JSON object per line."""

    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as output_file:
            temporary_path = Path(output_file.name)
            for record in records:
                output_file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                count += 1
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return count


def read_jsonl(path: Path, parser: Callable[[dict[str, Any]], RecordType]) -> list[RecordType]:
    """Load and validate JSONL records, reporting the failing line number."""

    records: list[RecordType] = []
    with path.open(encoding="utf-8") as input_file:
        for line_number, line in enumerate(input_file, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                records.append(parser(value))
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                raise ValueError(f"invalid record at {path}:{line_number}: {error}") from error
    return records
