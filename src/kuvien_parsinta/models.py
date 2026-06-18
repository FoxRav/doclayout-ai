"""Domain models."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from kuvien_parsinta.layout.structure import StructuredDocument


class InputKind(str, Enum):
    IMAGE = "image"
    PDF = "pdf"
    UNKNOWN = "unknown"


class OutputMode(str, Enum):
    """flowing = lehtileike-style article; structural = layout with pages/tables."""

    FLOWING = "flowing"
    STRUCTURAL = "structural"
    AUTO = "auto"


class QualityMode(str, Enum):
    """Parse quality vs speed trade-off."""

    STANDARD = "standard"
    MAX = "max"


class PdfMode(str, Enum):
    """Layout PDF rendering strategy."""

    STRUCTURAL = "structural"
    FACSIMILE = "facsimile"
    REBUILD = "rebuild"  # deprecated alias → structural
    CLEAN = "clean"
    ALL = "all"


class ParseEngineChoice(str, Enum):
    """Which parse engine(s) to run."""

    AUTO = "auto"
    HYBRID = "hybrid"
    STRUCTUREV3 = "structurev3"
    VL = "vl"
    BEST = "best"


class ParseResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    source: Path
    markdown_path: Path
    pdf_path: Path | None = None
    structural_pdf_path: Path | None = None
    facsimile_pdf_path: Path | None = None
    rebuild_pdf_path: Path | None = None
    clean_pdf_path: Path | None = None
    layout_debug_path: Path | None = None
    structural_debug_path: Path | None = None
    structural_report_path: Path | None = None
    search_text_path: Path | None = None
    ocr_overlay_debug_path: Path | None = None  # deprecated; use structural_debug_path
    engine_used: str
    primary_engine: str
    fallback_engine: str | None = None
    languages_tried: tuple[str, ...] = ()
    ocr_confidence_avg: float | None = None
    page_count: int = 1
    uses_layout_pdf: bool = False
    engine_requested: str | None = None
    engines_run: tuple[str, ...] = ()
    fallback_used: bool = False
    fallback_reason: str | None = None
    debug_artifacts: tuple[Path, ...] = ()
    vl_markdown_path: Path | None = None
    raw_json_path: Path | None = None
    compare_report_path: Path | None = None
    hybrid_json_path: Path | None = None
    layout_document: StructuredDocument | None = None
    text_source: str | None = None
    layout_source: str | None = None
    layout_helper_engine: str | None = None
    quality_mode: str | None = None
    quality_passed: bool | None = None
    quality_status: str | None = None
    quality_report_path: Path | None = None
