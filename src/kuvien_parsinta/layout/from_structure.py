"""Build StructuredDocument from PP-StructureV3 parsing_res_list."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Sequence

from kuvien_parsinta.encoding import fix_mojibake
from kuvien_parsinta.flow import LayoutLine
from kuvien_parsinta.layout.photo_crop import CropRect, crop_photo_by_rect
from kuvien_parsinta.layout.structure import (
    LayoutBlockKind,
    StructuredBlock,
    StructuredDocument,
    column_split_threshold,
    structured_to_markdown,
)

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
_IMAGE_LABELS = frozenset({"image", "figure"})
_SKIP_LABELS = frozenset(
    {
        "header",
        "footer",
        "number",
        "footnote",
        "header_image",
        "footer_image",
        "formula_number",
    }
)
_META_TEXT_RE = re.compile(r"^Sivu\s+\d+$", re.IGNORECASE)
_FULL_WIDTH_RATIO = 0.62
_COLUMN_GAP_RATIO = 0.12


def structure_document_from_parsing(
    parsing_res_list: Sequence[dict[str, Any]],
    *,
    image_path: Path | None = None,
    page_width: int = 0,
) -> StructuredDocument:
    ordered = _sorted_blocks(parsing_res_list)
    title = _extract_title(ordered)
    embedded_photo = _extract_photo_bbox(ordered, page_width=page_width)

    text_blocks = [
        block
        for block in ordered
        if _block_label(block) in _TEXT_LABELS
        and not _META_TEXT_RE.match(_block_content(block).strip())
    ]
    if not text_blocks:
        return StructuredDocument(title=title, blocks=(), embedded_photo=embedded_photo)

    page_w = float(page_width or _page_width_from_blocks(ordered))
    threshold = _column_threshold_from_blocks(text_blocks, page_width=page_w)
    photo_on_left = embedded_photo is not None and embedded_photo.x < page_w * 0.45

    left: list[tuple[str, float]] = []
    right: list[tuple[str, float]] = []
    full: list[tuple[str, float]] = []

    for block in text_blocks:
        content = _block_content(block).strip()
        if not content:
            continue
        bbox = _block_bbox(block)
        if bbox is None:
            full.append((content, 0.0))
            continue
        x1, _y1, x2, _y2 = bbox
        width = x2 - x1
        center = (x1 + x2) / 2
        y_min = float(bbox[1])
        if threshold is None and photo_on_left and center > page_w * 0.45:
            right.append((content, y_min))
            continue
        if threshold is None or width >= page_w * _FULL_WIDTH_RATIO:
            full.append((content, y_min))
            continue
        if center < threshold:
            left.append((content, y_min))
        else:
            right.append((content, y_min))

    blocks: list[StructuredBlock] = []
    if left:
        blocks.append(_text_column_block(left, column_index=0))
    if right:
        blocks.append(_text_column_block(right, column_index=1))
    if full:
        paragraphs = tuple(content for content, _y in sorted(full, key=lambda item: item[1]))
        blocks.append(
            StructuredBlock(
                kind=LayoutBlockKind.FULL_WIDTH,
                column_index=None,
                paragraphs=paragraphs,
                y_min=min(y for _c, y in full),
            )
        )
    return StructuredDocument(
        title=title,
        blocks=tuple(sorted(blocks, key=lambda block: block.y_min)),
        embedded_photo=embedded_photo,
    )


def structure_document_from_json(
    json_path: Path,
    *,
    image_path: Path | None = None,
) -> StructuredDocument:
    from kuvien_parsinta.ocr.structure import load_structure_json, normalize_parsing_blocks

    payload = load_structure_json(json_path)
    parsing = normalize_parsing_blocks(payload.get("parsing_res_list"))
    page_width = int(payload.get("width") or 0)
    return structure_document_from_parsing(
        parsing,
        image_path=image_path,
        page_width=page_width,
    )


def markdown_from_structure(
    document: StructuredDocument,
    *,
    output_mode: str,
) -> tuple[str, bool]:
    """Return markdown text and whether layout-faithful PDF should be used."""
    if output_mode == "flowing":
        return flowing_markdown_from_document(document), False
    if output_mode == "structural":
        return structured_to_markdown(document), True
    # auto
    if document.is_multi_column or document.embedded_photo is not None:
        return structured_to_markdown(document), True
    return flowing_markdown_from_document(document), False


def flowing_markdown_from_document(document: StructuredDocument) -> str:
    parts: list[str] = [f"# {document.title.strip()}", ""]
    paragraphs: list[tuple[float, str]] = []
    for block in document.blocks:
        for paragraph in block.paragraphs:
            cleaned = paragraph.strip()
            if cleaned:
                paragraphs.append((block.y_min, cleaned))
    for _y, paragraph in sorted(paragraphs, key=lambda item: item[0]):
        parts.extend((paragraph, ""))
    return fix_mojibake("\n".join(parts).rstrip() + "\n")


def save_embedded_photo(
    *,
    image_path: Path,
    document: StructuredDocument,
    output_path: Path,
) -> Path | None:
    if document.embedded_photo is None:
        return None
    return crop_photo_by_rect(
        image_path=image_path,
        crop=document.embedded_photo,
        output_path=output_path,
    )


def _sorted_blocks(blocks: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    def sort_key(block: dict[str, Any]) -> tuple[int, float]:
        order = block.get("block_order")
        order_num = int(order) if isinstance(order, int | float) else 9999
        bbox = _block_bbox(block)
        y = float(bbox[1]) if bbox is not None else 0.0
        return (order_num, y)

    return sorted(blocks, key=sort_key)


def _extract_title(blocks: Sequence[dict[str, Any]]) -> str:
    for block in blocks:
        if _block_label(block) in _TITLE_LABELS:
            content = _block_content(block).strip()
            if content:
                return fix_mojibake(content)
    for block in blocks:
        if _block_label(block) in _TEXT_LABELS:
            content = _block_content(block).strip()
            if content:
                return fix_mojibake(content.split(".")[0][:120])
    return "Asiakirja"


def _extract_photo_bbox(
    blocks: Sequence[dict[str, Any]],
    *,
    page_width: int,
) -> CropRect | None:
    best: CropRect | None = None
    best_area = 0.0
    page_area = max(1.0, float(page_width) * float(page_width))
    for block in blocks:
        if _block_label(block) not in _IMAGE_LABELS:
            continue
        bbox = _block_bbox(block)
        if bbox is None:
            continue
        crop = _crop_from_bbox(bbox)
        area = crop.width * crop.height
        area_ratio = area / page_area
        if area_ratio < 0.02 or area_ratio > 0.55:
            continue
        if area > best_area:
            best_area = area
            best = crop
    return best


def _text_column_block(
    items: list[tuple[str, float]],
    *,
    column_index: int,
) -> StructuredBlock:
    ordered = sorted(items, key=lambda item: item[1])
    paragraphs = tuple(content for content, _y in ordered)
    return StructuredBlock(
        kind=LayoutBlockKind.COLUMN,
        column_index=column_index,
        paragraphs=paragraphs,
        y_min=min(y for _c, y in ordered),
    )


def _column_threshold_from_blocks(
    blocks: Sequence[dict[str, Any]],
    *,
    page_width: float,
) -> float | None:
    lines: list[LayoutLine] = []
    for block in blocks:
        bbox = _block_bbox(block)
        if bbox is None:
            continue
        x1, y1, x2, y2 = bbox
        lines.append(
            LayoutLine(
                text=_block_content(block),
                y_min=y1,
                y_max=y2,
                x_min=x1,
                x_max=x2,
            )
        )
    if len(lines) < 2:
        return None
    if page_width > 0:
        narrow = [line for line in lines if line.width < page_width * _FULL_WIDTH_RATIO]
        if len(narrow) >= 2:
            return column_split_threshold(narrow)
    return column_split_threshold(lines)


def _page_width_from_blocks(blocks: Sequence[dict[str, Any]]) -> int:
    max_x = 0.0
    for block in blocks:
        bbox = _block_bbox(block)
        if bbox is not None:
            max_x = max(max_x, float(bbox[2]))
    return int(max_x) if max_x > 0 else 1280


def _block_label(block: dict[str, Any]) -> str:
    label = block.get("block_label")
    if isinstance(label, str):
        return label
    label = block.get("label")
    return label if isinstance(label, str) else ""


def _block_content(block: dict[str, Any]) -> str:
    content = block.get("block_content")
    if isinstance(content, str):
        return content
    content = block.get("content")
    return content if isinstance(content, str) else ""


def _block_bbox(block: dict[str, Any]) -> tuple[float, float, float, float] | None:
    raw = block.get("block_bbox")
    if raw is None:
        raw = block.get("bbox")
    if not isinstance(raw, list | tuple) or len(raw) < 4:
        return None
    return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))


def _crop_from_bbox(bbox: tuple[float, float, float, float]) -> CropRect:
    x1, y1, x2, y2 = bbox
    return CropRect(
        x=max(0, int(x1)),
        y=max(0, int(y1)),
        width=max(1, int(x2 - x1)),
        height=max(1, int(y2 - y1)),
    )


def uses_layout_pdf_from_parsing(parsing_res_list: Sequence[dict[str, Any]]) -> bool:
    document = structure_document_from_parsing(parsing_res_list)
    return document.is_multi_column or document.embedded_photo is not None
