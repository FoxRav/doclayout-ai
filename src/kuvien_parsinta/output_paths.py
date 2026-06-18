"""Output directory resolution."""

from __future__ import annotations

from pathlib import Path


def resolve_output_dir(source: Path, out_dir: Path | None = None) -> Path:
    """Return directory for markdown/PDF; defaults to the input file's folder."""
    if out_dir is not None:
        return out_dir.resolve()
    return source.parent
