"""Shared types for parse engines."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from kuvien_parsinta.fallback import ParseEngine
from kuvien_parsinta.layout.structure import StructuredDocument


@dataclass(frozen=True, slots=True)
class EngineRunOutput:
    engine: ParseEngine
    markdown_text: str
    confidence_avg: float
    page_count: int
    uses_layout_pdf: bool
    primary_engine: str = ""
    fallback_engine: str | None = None
    languages_tried: tuple[str, ...] = ()
    structure_json_path: Path | None = None
    structurev3_json_path: Path | None = None
    vl_json_path: Path | None = None
    vl_markdown_path: Path | None = None
    document: StructuredDocument | None = None
    layout_helper_document: StructuredDocument | None = None
    debug_paths: tuple[Path, ...] = field(default_factory=tuple)
    fallback_used: bool = False
    fallback_reason: str | None = None
    engines_run: tuple[str, ...] = field(default_factory=tuple)
    compare_report_path: Path | None = None
    hybrid_json_path: Path | None = None
    layout_helper_engine: str | None = None
    text_source: str | None = None
    layout_source: str | None = None
