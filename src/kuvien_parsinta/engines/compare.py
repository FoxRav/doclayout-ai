"""Engine comparison report for hybrid / best-mode runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kuvien_parsinta.engines.paddleocr_vl_engine import VlEngineOutput
from kuvien_parsinta.engines.structurev3_engine import StructureV3Output
from kuvien_parsinta.fallback import ParseEngine


def write_compare_report(
    *,
    target_dir: Path,
    stem: str,
    structure_out: StructureV3Output | None,
    vl_out: VlEngineOutput | None,
    selected_engine: ParseEngine,
    primary_engine: ParseEngine,
    conflicts: tuple[dict[str, Any], ...] = (),
    hybrid_json_path: Path | None = None,
) -> Path:
    """Write ``ocr/<stem>_compare_report.json`` summarising engine runs and conflicts."""
    ocr_dir = target_dir / "ocr"
    ocr_dir.mkdir(parents=True, exist_ok=True)
    report_path = ocr_dir / f"{stem}_compare_report.json"

    payload: dict[str, Any] = {
        "primary_engine": primary_engine.value,
        "selected_engine": selected_engine.value,
        "structurev3": _structure_summary(structure_out),
        "paddle_vl": _vl_summary(vl_out),
        "conflicts": list(conflicts),
        "hybrid_json_path": str(hybrid_json_path) if hybrid_json_path else None,
    }
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report_path


def _structure_summary(out: StructureV3Output | None) -> dict[str, Any] | None:
    if out is None:
        return None
    return {
        "ran": True,
        "confidence_avg": out.confidence_avg,
        "page_count": out.page_count,
        "uses_layout_pdf": out.uses_layout_pdf,
        "raw_json_path": str(out.structure_json_path),
        "languages_tried": list(out.languages_tried),
        "title": out.document.title,
        "markdown_chars": len(out.markdown_text),
    }


def merge_search_text_into_compare_report(
    report_path: Path,
    search_fields: dict[str, object],
) -> None:
    """Augment compare report with search-text dedup metadata."""
    if not report_path.is_file():
        return
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return
    payload.update(search_fields)
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def merge_layout_into_compare_report(
    report_path: Path,
    metrics_fields: dict[str, object],
) -> None:
    """Augment an existing compare report with layout quality metrics."""
    if not report_path.is_file():
        return
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return
    payload.update(metrics_fields)
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _vl_summary(out: VlEngineOutput | None) -> dict[str, Any] | None:
    if out is None:
        return None
    return {
        "ran": True,
        "confidence_avg": out.confidence_avg,
        "page_count": out.page_count,
        "uses_layout_pdf": out.uses_layout_pdf,
        "raw_json_path": str(out.vl_json_path),
        "vl_markdown_path": str(out.vl_markdown_path),
        "has_layout_document": out.document is not None,
        "markdown_chars": len(out.markdown_text),
    }
