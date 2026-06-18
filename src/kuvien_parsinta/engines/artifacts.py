"""Canonical raw JSON artefact paths."""

from __future__ import annotations

import shutil
from pathlib import Path


def alias_structure_json(*, source: Path, work_dir: Path, stem: str) -> Path:
    """Copy StructureV3 JSON to ``ocr/<stem>_structurev3_res.json`` for comparison runs."""
    work_dir.mkdir(parents=True, exist_ok=True)
    target = work_dir / f"{stem}_structurev3_res.json"
    if source.is_file() and source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target
