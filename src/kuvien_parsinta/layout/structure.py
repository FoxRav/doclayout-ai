"""Detect columns and build a layout-faithful document model from OCR boxes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Sequence

from kuvien_parsinta.encoding import fix_mojibake
from kuvien_parsinta.flow import (
    LayoutLine,
    dehyphenate_lines,
    extract_title,
    group_body_paragraphs,
    layout_lines_from_ocr,
    split_trailing_blocks,
)
from kuvien_parsinta.layout.photo_crop import CropRect, detect_embedded_photo


class LayoutBlockKind(str, Enum):
    HEADLINE = "headline"
    COLUMN = "column"
    FULL_WIDTH = "full_width"
    META = "meta"


@dataclass(frozen=True, slots=True)
class StructuredBlock:
    kind: LayoutBlockKind
    column_index: int | None
    paragraphs: tuple[str, ...]
    y_min: float


@dataclass(frozen=True, slots=True)
class StructuredDocument:
    title: str
    blocks: tuple[StructuredBlock, ...]
    embedded_photo: CropRect | None = None

    @property
    def is_multi_column(self) -> bool:
        column_indexes = {
            block.column_index
            for block in self.blocks
            if block.kind is LayoutBlockKind.COLUMN and block.column_index is not None
        }
        if len(column_indexes) >= 2:
            return True
        return self.embedded_photo is not None and bool(column_indexes)


_FULL_WIDTH_RATIO = 0.62
_COLUMN_GAP_RATIO = 0.12
_META_RE = re.compile(r"^Sivu\s+\d+$", re.IGNORECASE)


def detect_multi_column(lines: Sequence[LayoutLine]) -> bool:
    """True when OCR boxes suggest at least two text columns."""
    return column_split_threshold(lines) is not None


def column_split_threshold(lines: Sequence[LayoutLine]) -> float | None:
    """X coordinate that splits lines into left/right columns, if any."""
    return _column_threshold(list(lines))


def structure_document_from_ocr(
    *,
    texts: Sequence[str],
    polys: Sequence[Sequence[Sequence[float]]] | None,
    image_path: Path | None = None,
) -> StructuredDocument:
    lines = layout_lines_from_ocr(texts, polys)
    title, remaining = extract_title(lines)
    blocks = _structure_lines(remaining)
    if not blocks and title:
        blocks = (
            StructuredBlock(
                kind=LayoutBlockKind.FULL_WIDTH,
                column_index=None,
                paragraphs=(title,),
                y_min=0.0,
            ),
        )
        title = title.split(".")[0][:120]
    embedded_photo = (
        detect_embedded_photo(image_path, polys)
        if image_path is not None
        else None
    )
    return StructuredDocument(
        title=title,
        blocks=blocks,
        embedded_photo=embedded_photo,
    )


def structured_to_markdown(document: StructuredDocument) -> str:
    parts: list[str] = [f"# {document.title.strip()}", ""]
    for block in document.blocks:
        label = _block_label(block)
        if label:
            parts.extend((label, ""))
        for paragraph in block.paragraphs:
            cleaned = paragraph.strip()
            if cleaned:
                parts.extend((cleaned, ""))
    return fix_mojibake("\n".join(parts).rstrip() + "\n")


def _block_label(block: StructuredBlock) -> str | None:
    match block.kind:
        case LayoutBlockKind.COLUMN if block.column_index == 0:
            return "## Vasen palsta"
        case LayoutBlockKind.COLUMN if block.column_index == 1:
            return "## Oikea palsta"
        case LayoutBlockKind.FULL_WIDTH:
            return "## Leveä lohko"
        case LayoutBlockKind.META:
            return None
        case LayoutBlockKind.HEADLINE:
            return None
        case _:
            return None


def _structure_lines(lines: Sequence[LayoutLine]) -> tuple[StructuredBlock, ...]:
    if not lines:
        return ()

    merged = dehyphenate_lines(list(lines))
    body_lines, _dateline, _signature = split_trailing_blocks(merged)
    if not body_lines:
        return ()

    page_x_min = min(line.x_min for line in body_lines)
    page_x_max = max(line.x_max for line in body_lines)
    page_width = max(1.0, page_x_max - page_x_min)
    threshold = _column_threshold(body_lines)

    left_lines: list[LayoutLine] = []
    right_lines: list[LayoutLine] = []
    full_lines: list[LayoutLine] = []

    for line in body_lines:
        if _META_RE.match(line.text.strip()):
            continue
        if threshold is None or line.width >= page_width * _FULL_WIDTH_RATIO:
            full_lines.append(line)
            continue
        center = (line.x_min + line.x_max) / 2
        if center < threshold:
            left_lines.append(line)
        else:
            right_lines.append(line)

    blocks: list[StructuredBlock] = []
    if left_lines:
        blocks.append(_column_block(left_lines, column_index=0))
    if right_lines:
        blocks.append(_column_block(right_lines, column_index=1))
    if full_lines:
        paragraphs = group_body_paragraphs(dehyphenate_lines(full_lines))
        if paragraphs:
            blocks.append(
                StructuredBlock(
                    kind=LayoutBlockKind.FULL_WIDTH,
                    column_index=None,
                    paragraphs=tuple(paragraphs),
                    y_min=min(line.y_min for line in full_lines),
                )
            )
    return tuple(sorted(blocks, key=lambda block: block.y_min))


def _column_block(lines: list[LayoutLine], *, column_index: int) -> StructuredBlock:
    ordered = sorted(lines, key=lambda line: (line.y_min, line.x_min))
    paragraphs = group_body_paragraphs(dehyphenate_lines(ordered))
    return StructuredBlock(
        kind=LayoutBlockKind.COLUMN,
        column_index=column_index,
        paragraphs=tuple(paragraphs),
        y_min=min(line.y_min for line in ordered),
    )


def _column_threshold(lines: Sequence[LayoutLine]) -> float | None:
    if len(lines) < 3:
        return None
    page_x_min = min(line.x_min for line in lines)
    page_x_max = max(line.x_max for line in lines)
    page_width = max(1.0, page_x_max - page_x_min)

    narrow = [line for line in lines if line.width < page_width * _FULL_WIDTH_RATIO]
    if len(narrow) < 3:
        return None

    centers = sorted((line.x_min + line.x_max) / 2 for line in narrow)
    max_gap = 0.0
    split_at: float | None = None
    for left, right in zip(centers, centers[1:], strict=False):
        gap = right - left
        if gap > max_gap:
            max_gap = gap
            split_at = (left + right) / 2
    if split_at is None or max_gap < page_width * _COLUMN_GAP_RATIO:
        return None

    left_count = sum(1 for value in centers if value < split_at)
    right_count = len(centers) - left_count
    if left_count == 0 or right_count == 0:
        return None
    return split_at
