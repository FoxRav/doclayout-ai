"""Hybrid quality pipeline: VL text/structure + StructureV3 layout geometry."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from kuvien_parsinta.config import Settings
from kuvien_parsinta.engines.layout_merge import (
    _body_paragraphs_from_markdown,
    _title_from_markdown,
    merge_vl_text_with_structure_layout,
)
from kuvien_parsinta.engines.paddleocr_vl_engine import VlEngineOutput
from kuvien_parsinta.engines.structurev3_engine import StructureV3Output
from kuvien_parsinta.fallback import ParseEngine
from kuvien_parsinta.layout.from_structure import markdown_from_structure
from kuvien_parsinta.layout.structure import StructuredDocument
from kuvien_parsinta.models import OutputMode

logger = structlog.get_logger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class HybridMergeResult:
    markdown_text: str
    pdf_document: StructuredDocument | None
    uses_layout_pdf: bool
    confidence_avg: float
    conflicts: tuple[dict[str, Any], ...]
    hybrid_json_path: Path
    text_source: str
    layout_source: str
    title: str


def merge_hybrid_outputs(
    *,
    source_stem: str,
    target_dir: Path,
    vl_out: VlEngineOutput | None,
    structure_out: StructureV3Output | None,
    settings: Settings,
    output_mode: OutputMode,
) -> HybridMergeResult:
    """Combine VL understanding with StructureV3 layout into one result."""
    conflicts = _detect_conflicts(vl_out=vl_out, structure_out=structure_out, settings=settings)

    text_source = _resolve_text_source(vl_out, structure_out, settings)
    layout_source = _resolve_layout_source(vl_out, structure_out, settings)

    vl_markdown = vl_out.markdown_text if vl_out is not None else ""
    structure_md = structure_out.markdown_text if structure_out is not None else ""
    primary_md = vl_markdown if text_source == ParseEngine.PADDLE_VL.value else structure_md

    structure_doc = structure_out.document if structure_out is not None else None
    pdf_document = _build_pdf_document(
        vl_out=vl_out,
        structure_doc=structure_doc,
        vl_markdown=primary_md,
        settings=settings,
    )

    markdown_text, uses_layout_pdf = _build_markdown(
        primary_md=primary_md,
        pdf_document=pdf_document,
        structure_out=structure_out,
        output_mode=output_mode,
        settings=settings,
    )

    title = _resolve_title(vl_markdown=primary_md, structure_doc=structure_doc, conflicts=conflicts)
    confidence = _blend_confidence(vl_out, structure_out)

    hybrid_json_path = _save_hybrid_json(
        target_dir=target_dir,
        stem=source_stem,
        payload={
            "mode": ParseEngine.HYBRID.value,
            "text_source": text_source,
            "layout_source": layout_source,
            "reading_order_source": (
                ParseEngine.PADDLE_VL.value
                if settings.use_vl_for_reading_order and vl_out is not None
                else ParseEngine.PP_STRUCTURE.value
            ),
            "title": title,
            "conflicts": list(conflicts),
            "sources": {
                "vl_json": str(vl_out.vl_json_path) if vl_out else None,
                "structurev3_json": (
                    str(structure_out.structure_json_path) if structure_out else None
                ),
            },
            "confidence_avg": confidence,
            "uses_layout_pdf": uses_layout_pdf,
        },
    )

    logger.info(
        "hybrid_merge_done",
        text_source=text_source,
        layout_source=layout_source,
        conflicts=len(conflicts),
        hybrid_json=str(hybrid_json_path),
    )

    return HybridMergeResult(
        markdown_text=markdown_text,
        pdf_document=pdf_document,
        uses_layout_pdf=uses_layout_pdf,
        confidence_avg=confidence,
        conflicts=conflicts,
        hybrid_json_path=hybrid_json_path,
        text_source=text_source,
        layout_source=layout_source,
        title=title,
    )


def _build_pdf_document(
    *,
    vl_out: VlEngineOutput | None,
    structure_doc: StructuredDocument | None,
    vl_markdown: str,
    settings: Settings,
) -> StructuredDocument | None:
    if not settings.use_structurev3_for_pdf_geometry or structure_doc is None:
        if vl_out is not None and vl_out.document is not None:
            return vl_out.document
        return structure_doc

    if not vl_markdown.strip():
        return structure_doc

    merged = merge_vl_text_with_structure_layout(structure_doc, vl_markdown)
    if settings.use_structurev3_for_images and structure_doc.embedded_photo is not None:
        merged = StructuredDocument(
            title=merged.title,
            blocks=merged.blocks,
            embedded_photo=structure_doc.embedded_photo,
        )
    return merged


def _build_markdown(
    *,
    primary_md: str,
    pdf_document: StructuredDocument | None,
    structure_out: StructureV3Output | None,
    output_mode: OutputMode,
    settings: Settings,
) -> tuple[str, bool]:
    if not settings.use_vl_for_text:
        if structure_out is not None:
            return structure_out.markdown_text, structure_out.uses_layout_pdf
        return primary_md, False

    if pdf_document is None or structure_out is None:
        uses_layout = structure_out.uses_layout_pdf if structure_out else False
        return primary_md, uses_layout

    if output_mode is OutputMode.FLOWING:
        return primary_md, structure_out.uses_layout_pdf

    if output_mode is OutputMode.AUTO and structure_out.uses_layout_pdf:
        return primary_md, True

    if output_mode is OutputMode.STRUCTURAL:
        md, uses_layout = markdown_from_structure(
            pdf_document,
            output_mode=output_mode.value,
        )
        if md.strip():
            return md, uses_layout

    return primary_md, structure_out.uses_layout_pdf


def _resolve_title(
    *,
    vl_markdown: str,
    structure_doc: StructuredDocument | None,
    conflicts: tuple[dict[str, Any], ...],
) -> str:
    vl_title = _title_from_markdown(vl_markdown)
    for conflict in conflicts:
        if conflict.get("type") == "title" and conflict.get("resolution") == "vl":
            return str(conflict.get("vl") or vl_title)
    if vl_title:
        return vl_title
    if structure_doc is not None:
        return structure_doc.title
    return ""


def _resolve_text_source(
    vl_out: VlEngineOutput | None,
    structure_out: StructureV3Output | None,
    settings: Settings,
) -> str:
    if settings.use_vl_for_text and vl_out is not None:
        return ParseEngine.PADDLE_VL.value
    if structure_out is not None:
        return ParseEngine.PP_STRUCTURE.value
    return ParseEngine.PADDLE_VL.value


def _resolve_layout_source(
    vl_out: VlEngineOutput | None,
    structure_out: StructureV3Output | None,
    settings: Settings,
) -> str:
    if settings.use_structurev3_for_layout and structure_out is not None:
        return ParseEngine.PP_STRUCTURE.value
    if vl_out is not None and vl_out.document is not None:
        return ParseEngine.PADDLE_VL.value
    if structure_out is not None:
        return ParseEngine.PP_STRUCTURE.value
    return ParseEngine.PADDLE_VL.value


def _blend_confidence(
    vl_out: VlEngineOutput | None,
    structure_out: StructureV3Output | None,
) -> float:
    values: list[float] = []
    if vl_out is not None:
        values.append(vl_out.confidence_avg)
    if structure_out is not None:
        values.append(structure_out.confidence_avg)
    if not values:
        return 0.0
    return sum(values) / len(values)


def _detect_conflicts(
    *,
    vl_out: VlEngineOutput | None,
    structure_out: StructureV3Output | None,
    settings: Settings,
) -> tuple[dict[str, Any], ...]:
    if vl_out is None or structure_out is None:
        return ()

    conflicts: list[dict[str, Any]] = []
    vl_title = _title_from_markdown(vl_out.markdown_text)
    s_title = structure_out.document.title.strip()
    if vl_title and s_title and _normalize(vl_title) != _normalize(s_title):
        conflicts.append(
            {
                "type": "title",
                "vl": vl_title,
                "structurev3": s_title,
                "resolution": "vl",
            }
        )

    if settings.use_vl_for_text:
        vl_body = _normalize(_body_paragraphs_from_markdown(vl_out.markdown_text))
        s_body = _normalize(_body_paragraphs_from_markdown(structure_out.markdown_text))
        if vl_body and s_body and vl_body != s_body:
            conflicts.append(
                {
                    "type": "text",
                    "resolution": "vl",
                    "vl_chars": len(vl_out.markdown_text),
                    "structurev3_chars": len(structure_out.markdown_text),
                }
            )

    if settings.use_structurev3_for_layout:
        vl_cols = _column_count(vl_out.document)
        s_cols = _column_count(structure_out.document)
        if vl_cols > 0 and s_cols > 0 and vl_cols != s_cols:
            conflicts.append(
                {
                    "type": "layout",
                    "vl_columns": vl_cols,
                    "structurev3_columns": s_cols,
                    "resolution": "structurev3",
                }
            )

    return tuple(conflicts)


def _column_count(document: StructuredDocument | None) -> int:
    if document is None:
        return 0
    if document.is_multi_column:
        indexes = {
            block.column_index
            for block in document.blocks
            if block.column_index is not None
        }
        return max(len(indexes), 1)
    return 1


def _normalize(text: str | tuple[str, ...]) -> str:
    if isinstance(text, tuple):
        joined = " ".join(text)
    else:
        joined = text
    return _WHITESPACE_RE.sub(" ", joined.strip().lower())


def _save_hybrid_json(*, target_dir: Path, stem: str, payload: dict[str, Any]) -> Path:
    ocr_dir = target_dir / "ocr"
    ocr_dir.mkdir(parents=True, exist_ok=True)
    path = ocr_dir / f"{stem}_hybrid_res.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
