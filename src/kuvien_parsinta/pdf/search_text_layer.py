"""Normalized search text for facsimile PDF invisible layer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from rapidfuzz import fuzz

from kuvien_parsinta.encoding import fix_mojibake
from kuvien_parsinta.layout.from_structure import _block_bbox, _block_content, _block_label
from kuvien_parsinta.layout.page_layout import (
    BlockRenderMode,
    BboxPx,
    DocumentType,
    LayoutBlock,
    NewspaperBlockType,
    PageLayout,
)
from kuvien_parsinta.layout.page_layout_builder import _bbox_iou, _classify_block, _load_blocks, _make_layout_block

_DEDUP_RATIO_THRESHOLD = 88
_DEDUP_PARTIAL_THRESHOLD = 92
_MIN_SUBSTRING_LEN = 15

_NEWSPAPER_READING_ORDER: dict[NewspaperBlockType, int] = {
    NewspaperBlockType.MASTHEAD_LOGO: 0,
    NewspaperBlockType.NEWSPAPER_NAME: 1,
    NewspaperBlockType.ISSUE_META: 2,
    NewspaperBlockType.MAIN_HEADLINE: 3,
    NewspaperBlockType.SECONDARY_HEADLINE: 4,
    NewspaperBlockType.IMAGE_CAPTION: 5,
    NewspaperBlockType.RIGHT_SIDEBAR: 6,
    NewspaperBlockType.BODY_TEXT: 7,
    NewspaperBlockType.BOTTOM_HEADLINE: 8,
    NewspaperBlockType.BOTTOM_COLUMNS: 9,
    NewspaperBlockType.CONTINUATION_BOX: 10,
    NewspaperBlockType.FOOTER_BAR: 11,
    NewspaperBlockType.MARGIN_ARTIFACT: 12,
    NewspaperBlockType.UNKNOWN: 13,
}

_REGION_GROUPS: dict[NewspaperBlockType, str] = {
    NewspaperBlockType.MASTHEAD_LOGO: "masthead",
    NewspaperBlockType.NEWSPAPER_NAME: "masthead",
    NewspaperBlockType.ISSUE_META: "masthead",
    NewspaperBlockType.MAIN_HEADLINE: "headline",
    NewspaperBlockType.SECONDARY_HEADLINE: "headline",
    NewspaperBlockType.BOTTOM_HEADLINE: "headline",
    NewspaperBlockType.RIGHT_SIDEBAR: "right_sidebar",
    NewspaperBlockType.BOTTOM_COLUMNS: "bottom_columns",
    NewspaperBlockType.IMAGE_CAPTION: "caption",
    NewspaperBlockType.BODY_TEXT: "body",
    NewspaperBlockType.CONTINUATION_BOX: "continuation",
    NewspaperBlockType.FOOTER_BAR: "footer",
}


@dataclass(frozen=True, slots=True)
class RemovedDuplicate:
    kept_block_id: str
    removed_block_id: str
    similarity: float
    reason: str
    kept_preview: str
    removed_preview: str


@dataclass(frozen=True, slots=True)
class SearchTextLayer:
    segments: tuple[str, ...]
    full_text: str
    removed_duplicates: tuple[RemovedDuplicate, ...]
    block_count_before: int
    block_count_after: int

    def to_compare_fields(self) -> dict[str, object]:
        return {
            "search_text_block_count_before": self.block_count_before,
            "search_text_block_count_after": self.block_count_after,
            "search_text_dedup_removed_count": len(self.removed_duplicates),
            "search_text_dedup_removed": [
                {
                    "kept_block_id": item.kept_block_id,
                    "removed_block_id": item.removed_block_id,
                    "similarity": round(item.similarity, 1),
                    "reason": item.reason,
                    "kept_preview": item.kept_preview,
                    "removed_preview": item.removed_preview,
                }
                for item in self.removed_duplicates
            ],
        }


def build_search_text_layer(
    *,
    layout: PageLayout,
    vl_json_path: Path | None = None,
) -> SearchTextLayer:
    """Build deduplicated, reading-ordered text for facsimile search layer."""
    candidates = _collect_text_blocks(layout=layout, vl_json_path=vl_json_path)
    before_count = len(candidates)
    kept, removed = _deduplicate_blocks(candidates)
    ordered = _sort_for_reading_order(kept, document_type=layout.document_type)
    segments = tuple(_normalize_segment(block.text) for block in ordered if block.text.strip())
    full_text = "\n\n".join(segments)
    return SearchTextLayer(
        segments=segments,
        full_text=full_text,
        removed_duplicates=tuple(removed),
        block_count_before=before_count,
        block_count_after=len(segments),
    )


def deduplicated_layout_blocks(
    *,
    layout: PageLayout,
    vl_json_path: Path | None = None,
) -> tuple[LayoutBlock, ...]:
    """Return VL-enriched, deduplicated layout blocks in newspaper reading order."""
    candidates = _collect_text_blocks(layout=layout, vl_json_path=vl_json_path)
    kept, _removed = _deduplicate_blocks(candidates)
    ordered = _sort_for_reading_order(kept, document_type=layout.document_type)
    return tuple(ordered)


def save_search_text(*, layer: SearchTextLayer, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(layer.full_text + "\n", encoding="utf-8")
    return output_path


def _collect_text_blocks(*, layout: PageLayout, vl_json_path: Path | None) -> list[LayoutBlock]:
    blocks = [
        block
        for block in layout.blocks
        if block.render_mode is not BlockRenderMode.IMAGE and block.text.strip()
    ]
    if vl_json_path is None or not vl_json_path.is_file():
        return [_with_vl_resolved_text(block, block.text) for block in blocks]

    vl_blocks = _load_blocks(vl_json_path)
    enriched = [_enrich_block_text(block, vl_blocks) for block in blocks]
    existing_ids = {block.id for block in enriched}
    supplemented = _supplement_unmatched_vl_blocks(
        layout=layout,
        vl_blocks=vl_blocks,
        existing=enriched,
        existing_ids=existing_ids,
    )
    return enriched + supplemented


def _enrich_block_text(block: LayoutBlock, vl_blocks: Sequence[dict[str, object]]) -> LayoutBlock:
    best_text = block.text.strip()
    best_score = 0.0
    for vl_block in vl_blocks:
        bbox = _block_bbox(vl_block)
        if bbox is None:
            continue
        vl_text = fix_mojibake(_block_content(vl_block).strip())
        if not vl_text:
            continue
        iou = _bbox_iou(block.bbox_px, BboxPx(bbox[0], bbox[1], bbox[2], bbox[3]))
        fuzzy = fuzz.token_set_ratio(_normalize_for_match(best_text), _normalize_for_match(vl_text)) / 100.0
        score = iou * 0.55 + fuzzy * 0.45
        if score > best_score and (iou >= 0.08 or fuzzy >= 0.75):
            best_score = score
            best_text = vl_text
    return _with_vl_resolved_text(block, best_text)


def _supplement_unmatched_vl_blocks(
    *,
    layout: PageLayout,
    vl_blocks: Sequence[dict[str, object]],
    existing: list[LayoutBlock],
    existing_ids: set[str],
) -> list[LayoutBlock]:
    supplemented: list[LayoutBlock] = []
    for idx, vl_block in enumerate(vl_blocks):
        bbox = _block_bbox(vl_block)
        text = fix_mojibake(_block_content(vl_block).strip())
        if bbox is None or len(text) < 4:
            continue
        bbox_px = BboxPx(bbox[0], bbox[1], bbox[2], bbox[3])
        max_iou = max(
            (_bbox_iou(bbox_px, block.bbox_px) for block in existing),
            default=0.0,
        )
        if max_iou >= 0.12:
            continue
        block_type = _classify_block(
            label=_block_label(vl_block),
            bbox=bbox_px,
            page_width=layout.page_width_px,
            page_height=layout.page_height_px,
            text=text,
        )
        block_id = f"vl{idx}"
        if block_id in existing_ids:
            continue
        candidate = _make_layout_block(
            block_id=block_id,
            block_type=block_type,
            bbox_px=bbox_px,
            text=text,
            source_engine="paddleocr_vl",
            reading_order=10_000 + idx,
            page_width_px=layout.page_width_px,
            page_height_px=layout.page_height_px,
        )
        is_dup, _sim = _is_duplicate(candidate, existing)
        if is_dup:
            continue
        supplemented.append(candidate)
        existing.append(candidate)
        existing_ids.add(block_id)
    return supplemented


def _with_vl_resolved_text(block: LayoutBlock, text: str) -> LayoutBlock:
    if text == block.text:
        return block
    return LayoutBlock(
        id=block.id,
        block_type=block.block_type,
        bbox_px=block.bbox_px,
        bbox_pdf=block.bbox_pdf,
        text=text,
        source_engine="paddleocr_vl" if block.source_engine != "paddleocr_vl" else block.source_engine,
        confidence=max(block.confidence, 0.9),
        reading_order=block.reading_order,
        font_role=block.font_role,
        render_mode=block.render_mode,
    )


def _deduplicate_blocks(
    candidates: list[LayoutBlock],
) -> tuple[list[LayoutBlock], list[RemovedDuplicate]]:
    kept: list[LayoutBlock] = []
    removed: list[RemovedDuplicate] = []

    for block in candidates:
        text = block.text.strip()
        if not text:
            continue
        duplicate_idx: int | None = None
        best_similarity = 0.0
        for idx, existing in enumerate(kept):
            is_dup, similarity = _blocks_are_duplicates(block, existing)
            if is_dup:
                duplicate_idx = idx
                best_similarity = similarity
                break

        if duplicate_idx is None:
            kept.append(block)
            continue

        existing = kept[duplicate_idx]
        if _block_text_quality(block) > _block_text_quality(existing):
            removed.append(
                RemovedDuplicate(
                    kept_block_id=block.id,
                    removed_block_id=existing.id,
                    similarity=best_similarity,
                    reason="fuzzy_near_duplicate",
                    kept_preview=_preview(block.text),
                    removed_preview=_preview(existing.text),
                )
            )
            kept[duplicate_idx] = block
        else:
            removed.append(
                RemovedDuplicate(
                    kept_block_id=existing.id,
                    removed_block_id=block.id,
                    similarity=best_similarity,
                    reason="fuzzy_near_duplicate",
                    kept_preview=_preview(existing.text),
                    removed_preview=_preview(block.text),
                )
            )
    return kept, removed


def _is_duplicate(candidate: LayoutBlock, kept: list[LayoutBlock]) -> tuple[bool, float]:
    for block in kept:
        is_dup, sim = _blocks_are_duplicates(candidate, block)
        if is_dup:
            return True, sim
    return False, 0.0


def _blocks_are_duplicates(a: LayoutBlock, b: LayoutBlock) -> tuple[bool, float]:
    na = _normalize_for_match(a.text)
    nb = _normalize_for_match(b.text)
    if not na or not nb:
        return False, 0.0
    if na == nb:
        return True, 100.0

    ratio = float(fuzz.token_set_ratio(na, nb))
    partial = float(fuzz.partial_ratio(na, nb))
    spatial = _bboxes_near(a.bbox_px, b.bbox_px)
    same_region = _REGION_GROUPS.get(a.block_type) == _REGION_GROUPS.get(b.block_type)

    if ratio >= _DEDUP_RATIO_THRESHOLD and (spatial or same_region):
        return True, ratio
    if partial >= _DEDUP_PARTIAL_THRESHOLD and min(len(na), len(nb)) >= _MIN_SUBSTRING_LEN and spatial:
        return True, partial
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if (
        len(shorter) >= _MIN_SUBSTRING_LEN
        and shorter in longer
        and spatial
        and (same_region or ratio >= 75)
    ):
        return True, max(ratio, partial)
    return False, max(ratio, partial)


def _sort_for_reading_order(
    blocks: list[LayoutBlock],
    *,
    document_type: DocumentType,
) -> list[LayoutBlock]:
    if document_type is DocumentType.NEWSPAPER_FRONT_PAGE:
        return sorted(blocks, key=_newspaper_sort_key)
    return sorted(blocks, key=lambda block: (block.bbox_px.y1, block.bbox_px.x1, block.reading_order))


def _newspaper_sort_key(block: LayoutBlock) -> tuple[int, float, float]:
    type_rank = _NEWSPAPER_READING_ORDER.get(block.block_type, 99)
    if block.block_type is NewspaperBlockType.BOTTOM_COLUMNS:
        return (type_rank, block.bbox_px.x1, block.bbox_px.y1)
    if block.block_type is NewspaperBlockType.RIGHT_SIDEBAR:
        return (type_rank, block.bbox_px.y1, block.bbox_px.x1)
    return (type_rank, block.bbox_px.y1, block.bbox_px.x1)


def _block_text_quality(block: LayoutBlock) -> float:
    text = block.text.strip()
    score = float(len(text))
    score += block.confidence * 20.0
    if block.source_engine == "paddleocr_vl":
        score += 15.0
    if _looks_like_ocr_noise(text):
        score -= 25.0
    return score


def _looks_like_ocr_noise(text: str) -> bool:
    upper = text.upper()
    if "ERISTETTHIN" in upper:
        return True
    if re.search(r"(.)\1{3,}", text):
        return True
    return False


def _bboxes_near(a: BboxPx, b: BboxPx) -> bool:
    if _bbox_iou(a, b) > 0.12:
        return True
    vertical_overlap = max(0.0, min(a.y2, b.y2) - max(a.y1, b.y1))
    min_height = max(1.0, min(a.height, b.height))
    if vertical_overlap / min_height > 0.35:
        x_gap = max(0.0, max(a.x1, b.x1) - min(a.x2, b.x2))
        if x_gap < max(a.width, b.width) * 0.5:
            return True
    center_dx = abs(a.center_x - b.center_x)
    center_dy = abs(a.center_y - b.center_y)
    return center_dx < max(a.width, b.width) * 0.6 and center_dy < max(a.height, b.height) * 0.6


def _normalize_for_match(text: str) -> str:
    cleaned = fix_mojibake(text).lower()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned, flags=re.UNICODE)
    return " ".join(cleaned.split())


def _normalize_segment(text: str) -> str:
    lines = [line.strip() for line in fix_mojibake(text).splitlines() if line.strip()]
    if not lines:
        return fix_mojibake(text).strip()
    return "\n".join(lines)


def _preview(text: str, *, max_len: int = 72) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 1] + "…"
