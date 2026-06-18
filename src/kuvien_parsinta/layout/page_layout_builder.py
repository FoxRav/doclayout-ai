"""Build fixed-layout PageLayout from StructureV3 bboxes and VL text."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np

from kuvien_parsinta.encoding import fix_mojibake
from kuvien_parsinta.layout.from_structure import (
    _block_bbox,
    _block_content,
    _block_label,
    _sorted_blocks,
)
from kuvien_parsinta.layout.newspaper_layout import (
    CandidateBlock,
    detect_opencv_candidates,
    document_type_from_signals,
)
from kuvien_parsinta.layout.page_layout import (
    BlockRenderMode,
    BboxPx,
    DocumentType,
    FontRole,
    LayoutBlock,
    LayoutQualityMetrics,
    NewspaperBlockType,
    PageLayout,
)
from kuvien_parsinta.ocr.structure import load_structure_json, normalize_parsing_blocks
from kuvien_parsinta.pdf.coordinates import bbox_px_to_pdf, page_pdf_dimensions

_IMAGE_LABELS = frozenset({"image", "figure"})
_TITLE_LABELS = frozenset(
    {
        "doc_title",
        "paragraph_title",
        "content_title",
        "abstract_title",
        "reference_title",
        "figure_title",
        "table_title",
    }
)
_TEXT_LABELS = frozenset({"text", "content", "abstract", "reference_content", "aside_text"})
_SKIP_LABELS = frozenset({"header", "footer", "number", "footnote", "header_image", "footer_image"})

_DEBUG_COLORS: dict[NewspaperBlockType, tuple[int, int, int]] = {
    NewspaperBlockType.MASTHEAD_LOGO: (0, 0, 255),
    NewspaperBlockType.NEWSPAPER_NAME: (255, 0, 0),
    NewspaperBlockType.ISSUE_META: (0, 165, 255),
    NewspaperBlockType.MAIN_HEADLINE: (0, 255, 0),
    NewspaperBlockType.SECONDARY_HEADLINE: (0, 200, 100),
    NewspaperBlockType.HERO_IMAGE: (255, 0, 255),
    NewspaperBlockType.IMAGE_CAPTION: (255, 128, 0),
    NewspaperBlockType.RIGHT_SIDEBAR: (128, 0, 255),
    NewspaperBlockType.BOTTOM_HEADLINE: (0, 128, 255),
    NewspaperBlockType.BOTTOM_COLUMNS: (128, 128, 0),
    NewspaperBlockType.CONTINUATION_BOX: (64, 64, 255),
    NewspaperBlockType.BODY_TEXT: (180, 180, 180),
}


def build_page_layout(
    *,
    source_path: Path,
    structure_json_path: Path | None,
    vl_json_path: Path | None,
) -> PageLayout | None:
    """Build absolute-position page layout from engine JSON artefacts."""
    image = cv2.imread(str(source_path))
    if image is None:
        return None
    page_height_px, page_width_px = image.shape[:2]

    structure_blocks = _load_blocks(structure_json_path)
    vl_blocks = _load_blocks(vl_json_path)
    vl_text_by_bbox = _vl_text_map(vl_blocks)

    raw_blocks: list[tuple[dict[str, Any], str, float]] = []
    for idx, block in enumerate(_sorted_blocks(structure_blocks)):
        label = _block_label(block)
        if label in _SKIP_LABELS:
            continue
        bbox = _block_bbox(block)
        if bbox is None:
            continue
        text = _resolve_text(block, vl_text_by_bbox, bbox)
        raw_blocks.append((block, text, float(bbox[1])))

    raw_blocks.sort(key=lambda item: item[2])

    layout_blocks: list[LayoutBlock] = []
    for idx, (block, text, _y) in enumerate(raw_blocks):
        bbox = _block_bbox(block)
        if bbox is None:
            continue
        bbox_px = BboxPx(bbox[0], bbox[1], bbox[2], bbox[3])
        block_type = _classify_block(
            label=_block_label(block),
            bbox=bbox_px,
            page_width=page_width_px,
            page_height=page_height_px,
            text=text,
        )
        layout_blocks.append(
            _make_layout_block(
                block_id=f"s{idx}",
                block_type=block_type,
                bbox_px=bbox_px,
                text=text,
                source_engine="structurev3",
                reading_order=idx,
                page_width_px=page_width_px,
                page_height_px=page_height_px,
            )
        )

    _merge_opencv_candidates(
        layout_blocks=layout_blocks,
        candidates=detect_opencv_candidates(image),
        page_width_px=page_width_px,
        page_height_px=page_height_px,
    )

    pdf_w, pdf_h, scale_x, scale_y = page_pdf_dimensions(
        source_width_px=page_width_px,
        source_height_px=page_height_px,
    )

    final_blocks = tuple(
        LayoutBlock(
            id=block.id,
            block_type=block.block_type,
            bbox_px=block.bbox_px,
            bbox_pdf=bbox_px_to_pdf(
                block.bbox_px,
                pdf_height_pt=pdf_h,
                scale_x=scale_x,
                scale_y=scale_y,
            ),
            text=block.text,
            source_engine=block.source_engine,
            confidence=block.confidence,
            reading_order=block.reading_order,
            font_role=block.font_role,
            render_mode=block.render_mode,
        )
        for block in layout_blocks
    )

    doc_type = document_type_from_signals(
        page_width=page_width_px,
        page_height=page_height_px,
        block_types={block.block_type for block in final_blocks},
    )

    return PageLayout(
        page_width_px=page_width_px,
        page_height_px=page_height_px,
        pdf_width_pt=pdf_w,
        pdf_height_pt=pdf_h,
        scale_x=scale_x,
        scale_y=scale_y,
        document_type=doc_type,
        blocks=final_blocks,
    )


def save_layout_debug_image(
    *,
    source_path: Path,
    layout: PageLayout,
    output_path: Path,
) -> Path:
    """Write colour-coded bbox overlay for quick layout QA."""
    image = cv2.imread(str(source_path))
    if image is None:
        raise FileNotFoundError(f"Cannot read image: {source_path}")

    overlay = image.copy()
    for block in layout.blocks:
        color = _DEBUG_COLORS.get(block.block_type, (200, 200, 200))
        x1, y1, x2, y2 = (
            int(block.bbox_px.x1),
            int(block.bbox_px.y1),
            int(block.bbox_px.x2),
            int(block.bbox_px.y2),
        )
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            overlay,
            block.block_type.value[:12],
            (x1 + 2, max(12, y1 + 14)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            color,
            1,
            cv2.LINE_AA,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), overlay)
    return output_path


def layout_quality_metrics(
    *,
    layout: PageLayout,
    pdf_mode: str,
    layout_preserve: bool,
    reflow_used: bool,
    visible_text_overlay: bool = False,
    debug_boxes_visible: bool = False,
    visible_ocr: bool = False,
    raster_similarity_to_source: float | None = None,
) -> LayoutQualityMetrics:
    types = {block.block_type for block in layout.blocks}
    warnings: list[str] = []
    if layout.document_type is DocumentType.NEWSPAPER_FRONT_PAGE and reflow_used:
        warnings.append("reflow_used_on_newspaper_page")
    if NewspaperBlockType.HERO_IMAGE not in types:
        warnings.append("hero_image_not_found")
    if visible_text_overlay:
        warnings.append("visible_text_overlay_on_facsimile")
    if debug_boxes_visible:
        warnings.append("debug_boxes_on_facsimile")
    return LayoutQualityMetrics(
        document_type=layout.document_type,
        pdf_mode=pdf_mode,
        layout_preserve=layout_preserve,
        source_aspect_ratio=layout.page_width_px / max(1, layout.page_height_px),
        pdf_aspect_ratio=layout.pdf_width_pt / max(1.0, layout.pdf_height_pt),
        main_headline_found=(
            NewspaperBlockType.MAIN_HEADLINE in types
            or NewspaperBlockType.SECONDARY_HEADLINE in types
        ),
        hero_image_found=NewspaperBlockType.HERO_IMAGE in types,
        right_sidebar_found=NewspaperBlockType.RIGHT_SIDEBAR in types,
        bottom_columns_found=NewspaperBlockType.BOTTOM_COLUMNS in types,
        reflow_used=reflow_used,
        visible_text_overlay=visible_text_overlay,
        debug_boxes_visible=debug_boxes_visible,
        visible_ocr=visible_ocr,
        raster_similarity_to_source=raster_similarity_to_source,
        warnings=tuple(warnings),
    )


def _load_blocks(json_path: Path | None) -> tuple[dict[str, Any], ...]:
    if json_path is None or not json_path.is_file():
        return ()
    payload = load_structure_json(json_path)
    return normalize_parsing_blocks(payload.get("parsing_res_list"))


def _vl_text_map(vl_blocks: Sequence[dict[str, Any]]) -> list[tuple[BboxPx, str]]:
    mapped: list[tuple[BboxPx, str]] = []
    for block in vl_blocks:
        bbox = _block_bbox(block)
        text = fix_mojibake(_block_content(block).strip())
        if bbox is None or not text:
            continue
        mapped.append((BboxPx(bbox[0], bbox[1], bbox[2], bbox[3]), text))
    return mapped


def _resolve_text(
    block: dict[str, Any],
    vl_text_by_bbox: list[tuple[BboxPx, str]],
    bbox: tuple[float, float, float, float],
) -> str:
    target = BboxPx(bbox[0], bbox[1], bbox[2], bbox[3])
    best_text = ""
    best_iou = 0.0
    for vl_bbox, vl_text in vl_text_by_bbox:
        iou = _bbox_iou(target, vl_bbox)
        if iou > best_iou:
            best_iou = iou
            best_text = vl_text
    if best_iou >= 0.15 and best_text:
        return best_text
    return fix_mojibake(_block_content(block).strip())


def _bbox_iou(a: BboxPx, b: BboxPx) -> float:
    ix1 = max(a.x1, b.x1)
    iy1 = max(a.y1, b.y1)
    ix2 = min(a.x2, b.x2)
    iy2 = min(a.y2, b.y2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    union = a.area + b.area - inter
    return inter / union if union > 0 else 0.0


def _classify_block(
    *,
    label: str,
    bbox: BboxPx,
    page_width: int,
    page_height: int,
    text: str,
) -> NewspaperBlockType:
    page_w = float(page_width)
    page_h = float(page_height)
    rel_y = bbox.y1 / page_h
    rel_x_center = bbox.center_x / page_w
    width_ratio = bbox.width / page_w
    height_ratio = bbox.height / page_h
    upper = text.upper()

    if label in _IMAGE_LABELS:
        if bbox.area / (page_w * page_h) > 0.04:
            return NewspaperBlockType.HERO_IMAGE
        return NewspaperBlockType.IMAGE_CAPTION

    if "JATKUU" in upper and rel_y > 0.75:
        return NewspaperBlockType.CONTINUATION_BOX

    if rel_y < 0.08 and width_ratio > 0.5:
        if height_ratio < 0.035:
            return NewspaperBlockType.ISSUE_META
        if "KUVA" in upper or "SANOMAT" in upper:
            return NewspaperBlockType.NEWSPAPER_NAME
        return NewspaperBlockType.MASTHEAD_LOGO

    if label in _TITLE_LABELS or (width_ratio > 0.55 and height_ratio > 0.02):
        if rel_y < 0.22:
            return NewspaperBlockType.MAIN_HEADLINE
        if rel_y < 0.35:
            return NewspaperBlockType.SECONDARY_HEADLINE
        if rel_y > 0.65:
            return NewspaperBlockType.BOTTOM_HEADLINE

    if rel_x_center > 0.68 and width_ratio < 0.28 and rel_y < 0.8:
        return NewspaperBlockType.RIGHT_SIDEBAR

    if rel_y > 0.68 and width_ratio < 0.28:
        return NewspaperBlockType.BOTTOM_COLUMNS

    if rel_y > 0.92:
        return NewspaperBlockType.FOOTER_BAR

    return NewspaperBlockType.BODY_TEXT


def _font_role_for(block_type: NewspaperBlockType) -> FontRole:
    match block_type:
        case NewspaperBlockType.MASTHEAD_LOGO | NewspaperBlockType.NEWSPAPER_NAME:
            return FontRole.MASTHEAD
        case (
            NewspaperBlockType.MAIN_HEADLINE
            | NewspaperBlockType.SECONDARY_HEADLINE
            | NewspaperBlockType.BOTTOM_HEADLINE
        ):
            return FontRole.HEADLINE
        case NewspaperBlockType.IMAGE_CAPTION:
            return FontRole.CAPTION
        case NewspaperBlockType.ISSUE_META | NewspaperBlockType.CONTINUATION_BOX:
            return FontRole.META
        case _:
            return FontRole.BODY


def _render_mode_for(block_type: NewspaperBlockType) -> BlockRenderMode:
    if block_type is NewspaperBlockType.HERO_IMAGE:
        return BlockRenderMode.IMAGE
    if block_type is NewspaperBlockType.CONTINUATION_BOX:
        return BlockRenderMode.BOX
    return BlockRenderMode.TEXT


def _make_layout_block(
    *,
    block_id: str,
    block_type: NewspaperBlockType,
    bbox_px: BboxPx,
    text: str,
    source_engine: str,
    reading_order: int,
    page_width_px: int,
    page_height_px: int,
) -> LayoutBlock:
    pdf_w, pdf_h, scale_x, scale_y = page_pdf_dimensions(
        source_width_px=page_width_px,
        source_height_px=page_height_px,
    )
    return LayoutBlock(
        id=block_id,
        block_type=block_type,
        bbox_px=bbox_px,
        bbox_pdf=bbox_px_to_pdf(bbox_px, pdf_height_pt=pdf_h, scale_x=scale_x, scale_y=scale_y),
        text=text,
        source_engine=source_engine,
        confidence=0.85,
        reading_order=reading_order,
        font_role=_font_role_for(block_type),
        render_mode=_render_mode_for(block_type),
    )


def _merge_opencv_candidates(
    *,
    layout_blocks: list[LayoutBlock],
    candidates: tuple[CandidateBlock, ...],
    page_width_px: int,
    page_height_px: int,
) -> None:
    existing_types = {block.block_type for block in layout_blocks}
    order = len(layout_blocks)
    for idx, candidate in enumerate(candidates):
        if candidate.block_type in existing_types:
            if candidate.block_type not in {
                NewspaperBlockType.BOTTOM_COLUMNS,
                NewspaperBlockType.CONTINUATION_BOX,
            }:
                continue
        layout_blocks.append(
            _make_layout_block(
                block_id=f"cv{idx}",
                block_type=candidate.block_type,
                bbox_px=candidate.bbox,
                text="",
                source_engine="opencv",
                reading_order=order + idx,
                page_width_px=page_width_px,
                page_height_px=page_height_px,
            )
        )
        existing_types.add(candidate.block_type)
