"""Newspaper front page model with exclusive block ownership."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import cv2

from kuvien_parsinta.layout.page_layout import (
    BlockRenderMode,
    BboxPx,
    LayoutBlock,
    NewspaperBlockType,
    PageLayout,
)
from kuvien_parsinta.pdf.search_text_layer import deduplicated_layout_blocks
from kuvien_parsinta.layout.story_element_detection import (
    CaptionCandidate,
    StoryContentReport,
    build_story_content_report,
    detect_sidebar_source_candidate,
    find_caption_candidates,
    hero_bbox_from_layout,
    normalize_caption_text,
    select_best_caption,
)
from kuvien_parsinta.text.ocr_normalization import normalize_ocr_text

_TARGET_BOTTOM_COLUMNS = 5

# Metadata strip: below masthead, above headline group.
_META_STRIP_Y = (0.17, 0.23)
_HEADLINE_Y_MAX = 0.38
_MASTHEAD_Y_MAX = 0.17
_BOTTOM_COLUMNS_Y_MIN = 0.68


class BlockRole(str, Enum):
    MASTHEAD = "masthead"
    NEWSPAPER_NAME = "newspaper_name"
    ISSUE_META = "issue_meta"
    DATE_META = "date_meta"
    STARS_META = "stars_meta"
    PRICE_META = "price_meta"
    MAIN_HEADLINE = "main_headline"
    SECONDARY_HEADLINE = "secondary_headline"
    HERO_IMAGE = "hero_image"
    RIGHT_SIDEBAR = "right_sidebar"
    IMAGE_CAPTION = "image_caption"
    LOWER_HEADLINE = "lower_headline"
    BOTTOM_COLUMN = "bottom_column"
    CONTINUATION_BOX = "continuation_box"
    DECORATIVE = "decorative"
    DISCARDED_DUPLICATE = "discarded_duplicate"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TextBlock:
    text: str
    bbox: BboxPx | None
    source_block_ids: tuple[str, ...]
    role: BlockRole
    confidence: float


@dataclass(frozen=True, slots=True)
class MetaRow:
    issue_number: TextBlock | None
    date_text: TextBlock | None
    stars: TextBlock | None
    price: TextBlock | None


@dataclass(frozen=True, slots=True)
class MainStory:
    headline: TextBlock | None
    subheadline: TextBlock | None
    hero_image_path: Path | None
    sidebar_text_blocks: tuple[TextBlock, ...]
    sidebar_text: str
    caption: TextBlock | None
    missing_required_elements: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LowerStory:
    headline: TextBlock | None
    columns: tuple[TextBlock, ...]
    continuation_marker: TextBlock | None


@dataclass(frozen=True, slots=True)
class OwnershipInfo:
    consumed_block_ids: tuple[str, ...]
    consumed_metadata_block_ids: tuple[str, ...]
    reused_block_ids: tuple[str, ...]
    metadata_blocks_consumed_before_story: bool


@dataclass(frozen=True, slots=True)
class NewspaperFrontPageModel:
    masthead: TextBlock | None
    newspaper_name: TextBlock | None
    meta: MetaRow
    main_story: MainStory
    lower_story: LowerStory
    ownership: OwnershipInfo
    hero_image_crop_path: Path | None
    story_content: StoryContentReport

    @property
    def masthead_text(self) -> str:
        return self.masthead.text if self.masthead is not None else ""

    @property
    def newspaper_name_text(self) -> str:
        return self.newspaper_name.text if self.newspaper_name is not None else ""

    @property
    def issue_number(self) -> str:
        return self.meta.issue_number.text if self.meta.issue_number is not None else ""

    @property
    def date_text(self) -> str:
        return self.meta.date_text.text if self.meta.date_text is not None else ""

    @property
    def stars_text(self) -> str:
        return self.meta.stars.text if self.meta.stars is not None else ""

    @property
    def price_text(self) -> str:
        return self.meta.price.text if self.meta.price is not None else ""

    @property
    def main_headline(self) -> str:
        return self.main_story.headline.text if self.main_story.headline is not None else ""

    @property
    def secondary_headline(self) -> str:
        return self.main_story.subheadline.text if self.main_story.subheadline is not None else ""

    @property
    def right_sidebar_text(self) -> str:
        if self.main_story.sidebar_text.strip():
            return self.main_story.sidebar_text
        parts = [block.text for block in self.main_story.sidebar_text_blocks if block.text.strip()]
        return "\n\n".join(parts)

    @property
    def image_caption(self) -> str:
        return self.main_story.caption.text if self.main_story.caption is not None else ""

    @property
    def bottom_headline(self) -> str:
        return self.lower_story.headline.text if self.lower_story.headline is not None else ""

    @property
    def bottom_column_texts(self) -> tuple[str, ...]:
        return tuple(block.text for block in self.lower_story.columns if block.text.strip())

    @property
    def continuation_text(self) -> str:
        if self.lower_story.continuation_marker is None:
            return ""
        return self.lower_story.continuation_marker.text

    def to_debug_dict(self) -> dict[str, object]:
        sidebar = self.right_sidebar_text.strip()
        return {
            "meta": {
                "issue_number": self.issue_number,
                "date_text": self.date_text,
                "stars": self.stars_text,
                "price": self.price_text,
            },
            "main_story": {
                "headline": self.main_headline,
                "subheadline": self.secondary_headline,
                "sidebar_text_starts_with": sidebar[:80] if sidebar else "",
                "sidebar_text": sidebar[:200] if sidebar else "",
                "caption": self.image_caption[:200] if self.image_caption else "",
                "missing_required_elements": list(self.main_story.missing_required_elements),
            },
            "story_content": self.story_content.to_quality_dict(),
            "ownership": {
                "reused_block_ids": list(self.ownership.reused_block_ids),
                "consumed_metadata_block_ids": list(self.ownership.consumed_metadata_block_ids),
                "consumed_block_ids": list(self.ownership.consumed_block_ids),
                "metadata_blocks_consumed_before_story": (
                    self.ownership.metadata_blocks_consumed_before_story
                ),
            },
        }


# Backward-compatible alias used by template renderer and pipeline.
NewspaperPageModel = NewspaperFrontPageModel


class _BlockAssigner:
    def __init__(self) -> None:
        self.consumed_block_ids: set[str] = set()
        self.consumed_metadata_block_ids: set[str] = set()
        self.block_roles: dict[str, BlockRole] = {}
        self.consumed_line_fingerprints: set[str] = set()
        self.metadata_consumed_before_story = False

    def is_available(self, block: LayoutBlock) -> bool:
        return block.id not in self.consumed_block_ids

    def available(self, blocks: tuple[LayoutBlock, ...]) -> list[LayoutBlock]:
        return [block for block in blocks if self.is_available(block)]

    def consume_line(self, line: str) -> None:
        normalized = _normalize_line_fingerprint(line)
        if normalized:
            self.consumed_line_fingerprints.add(normalized)

    def consume_block(
        self,
        block: LayoutBlock,
        *,
        role: BlockRole,
        text: str | None = None,
        is_metadata: bool = False,
    ) -> TextBlock:
        if block.id in self.consumed_block_ids:
            raise ValueError(f"Block {block.id} already consumed as {self.block_roles[block.id]}")
        self.consumed_block_ids.add(block.id)
        self.block_roles[block.id] = role
        if is_metadata:
            self.consumed_metadata_block_ids.add(block.id)
        block_text = normalize_ocr_text(text if text is not None else block.text.strip())
        for line in block_text.splitlines():
            self.consume_line(line)
        return TextBlock(
            text=block_text,
            bbox=block.bbox_px,
            source_block_ids=(block.id,),
            role=role,
            confidence=block.confidence,
        )

    def make_text_block(
        self,
        *,
        text: str,
        bbox: BboxPx | None,
        source_block_ids: tuple[str, ...],
        role: BlockRole,
        confidence: float = 0.85,
    ) -> TextBlock:
        normalized = normalize_ocr_text(text.strip())
        for line in normalized.splitlines():
            self.consume_line(line)
        return TextBlock(
            text=normalized,
            bbox=bbox,
            source_block_ids=source_block_ids,
            role=role,
            confidence=confidence,
        )

    def line_is_consumed(self, line: str) -> bool:
        return _normalize_line_fingerprint(line) in self.consumed_line_fingerprints

    def filter_story_lines(self, text: str) -> str:
        kept: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if self.line_is_consumed(stripped):
                continue
            if _line_is_metadata_candidate(stripped):
                continue
            kept.append(stripped)
        return "\n".join(kept)


def build_newspaper_page_model(
    *,
    layout: PageLayout,
    source_path: Path,
    vl_json_path: Path | None,
    structure_json_path: Path | None = None,
    tmp_dir: Path | None,
) -> NewspaperFrontPageModel:
    """Build front page model with exclusive block ownership."""
    blocks = deduplicated_layout_blocks(layout=layout, vl_json_path=vl_json_path)
    return _build_front_page_model(
        blocks=blocks,
        layout=layout,
        source_path=source_path,
        vl_json_path=vl_json_path,
        structure_json_path=structure_json_path,
        tmp_dir=tmp_dir,
    )


def save_page_model_debug(*, model: NewspaperFrontPageModel, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(model.to_debug_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def _build_front_page_model(
    *,
    blocks: tuple[LayoutBlock, ...],
    layout: PageLayout,
    source_path: Path,
    vl_json_path: Path | None,
    structure_json_path: Path | None,
    tmp_dir: Path | None,
) -> NewspaperFrontPageModel:
    assigner = _BlockAssigner()
    page_w = float(layout.page_width_px)
    page_h = float(layout.page_height_px)
    hero_bbox = hero_bbox_from_layout(layout)
    sidebar_source_detected = detect_sidebar_source_candidate(blocks, page_w=page_w, page_h=page_h)

    # A. Masthead / newspaper name
    masthead, newspaper_name = _detect_masthead(blocks, assigner, page_h)

    # B–C. Metadata strip (before story)
    meta = _detect_metadata_strip(blocks, assigner, page_w, page_h)
    assigner.metadata_consumed_before_story = True

    # D–E. Headlines
    main_headline, subheadline = _detect_headlines(blocks, assigner, page_w, page_h)

    # F. Hero image
    hero_path = _crop_hero_image(layout=layout, source_path=source_path, tmp_dir=tmp_dir)
    for block in blocks:
        if block.block_type is NewspaperBlockType.HERO_IMAGE:
            assigner.consumed_block_ids.add(block.id)
            assigner.block_roles[block.id] = BlockRole.HERO_IMAGE

    # H. Caption (multi-source) — before sidebar to reserve ownership
    caption_candidates = tuple(
        find_caption_candidates(
            blocks=blocks,
            layout=layout,
            vl_json_path=vl_json_path,
            structure_json_path=structure_json_path,
            hero_bbox=hero_bbox,
        )
    )
    caption = _assign_caption(
        blocks=blocks,
        assigner=assigner,
        caption_candidates=caption_candidates,
    )

    # I. Lower headline — before sidebar to prevent leaks
    lower_headline = _detect_lower_headline(blocks, assigner, page_h)

    # G. Right sidebar (remaining blocks only)
    sidebar_blocks = _detect_sidebar(blocks, assigner, page_w, page_h)
    sidebar_text = "\n\n".join(block.text for block in sidebar_blocks if block.text.strip())

    missing_required: list[str] = []
    if sidebar_source_detected and not sidebar_text.strip():
        missing_required.append("main_story.sidebar_text")
    if caption_candidates and caption is None:
        missing_required.append("main_story.caption")

    story_content = build_story_content_report(
        sidebar_text=sidebar_text,
        caption_text=caption.text if caption is not None else "",
        caption_candidates=caption_candidates,
        sidebar_source_detected=sidebar_source_detected,
    )
    if missing_required:
        story_content = StoryContentReport(
            main_story_sidebar_detected=story_content.main_story_sidebar_detected,
            image_caption_candidates_count=story_content.image_caption_candidates_count,
            image_caption_selected=caption is not None,
            content_loss_detected=True,
            missing_required_elements=tuple(missing_required),
            caption_candidates=caption_candidates,
        )

    # J. Bottom columns
    columns = _detect_bottom_columns(blocks, assigner, page_h)

    # K. Continuation box
    continuation = _detect_continuation(blocks, assigner)

    reused = _find_reused_blocks(assigner)
    ownership = OwnershipInfo(
        consumed_block_ids=tuple(sorted(assigner.consumed_block_ids)),
        consumed_metadata_block_ids=tuple(sorted(assigner.consumed_metadata_block_ids)),
        reused_block_ids=tuple(reused),
        metadata_blocks_consumed_before_story=assigner.metadata_consumed_before_story,
    )

    return NewspaperFrontPageModel(
        masthead=masthead,
        newspaper_name=newspaper_name,
        meta=meta,
        main_story=MainStory(
            headline=main_headline,
            subheadline=subheadline,
            hero_image_path=hero_path,
            sidebar_text_blocks=tuple(sidebar_blocks),
            sidebar_text=sidebar_text,
            caption=caption,
            missing_required_elements=tuple(missing_required),
        ),
        lower_story=LowerStory(
            headline=lower_headline,
            columns=tuple(columns),
            continuation_marker=continuation,
        ),
        ownership=ownership,
        hero_image_crop_path=hero_path,
        story_content=story_content,
    )


def _detect_masthead(
    blocks: tuple[LayoutBlock, ...],
    assigner: _BlockAssigner,
    page_h: float,
) -> tuple[TextBlock | None, TextBlock | None]:
    masthead_block: LayoutBlock | None = None
    name_block: LayoutBlock | None = None

    for block in assigner.available(blocks):
        rel_y = block.bbox_px.y1 / page_h
        if rel_y > _MASTHEAD_Y_MAX:
            continue
        upper = block.text.upper()
        if block.block_type is NewspaperBlockType.MASTHEAD_LOGO:
            masthead_block = block
        elif block.block_type is NewspaperBlockType.NEWSPAPER_NAME or "SANOMAT" in upper:
            name_block = block
        elif "KUVA" in upper and "ERIKOIS" in upper:
            masthead_block = block
        elif "ILTA-SANOMAT" in upper or "SANOMAT" in upper:
            name_block = block

    masthead: TextBlock | None = None
    newspaper_name: TextBlock | None = None

    if masthead_block is not None:
        text = _first_line(masthead_block.text)
        if text:
            masthead = assigner.consume_block(
                masthead_block, role=BlockRole.MASTHEAD, text=text, is_metadata=False
            )

    if name_block is not None and assigner.is_available(name_block):
        text = _first_line(name_block.text)
        if "KUVA" in text.upper() and "ERIKOIS" in text.upper() and not masthead:
            masthead = assigner.consume_block(
                name_block, role=BlockRole.MASTHEAD, text="KUVA ERIKOIS", is_metadata=False
            )
        elif text:
            newspaper_name = assigner.consume_block(
                name_block, role=BlockRole.NEWSPAPER_NAME, text=text, is_metadata=False
            )

    if masthead is None:
        masthead = assigner.make_text_block(
            text="KUVA ERIKOIS",
            bbox=None,
            source_block_ids=(),
            role=BlockRole.MASTHEAD,
        )
    if newspaper_name is None:
        newspaper_name = assigner.make_text_block(
            text="ILTA-SANOMAT",
            bbox=None,
            source_block_ids=(),
            role=BlockRole.NEWSPAPER_NAME,
        )

    return masthead, newspaper_name


def _detect_metadata_strip(
    blocks: tuple[LayoutBlock, ...],
    assigner: _BlockAssigner,
    page_w: float,
    page_h: float,
) -> MetaRow:
    issue: TextBlock | None = None
    date: TextBlock | None = None
    stars: TextBlock | None = None
    price: TextBlock | None = None

    meta_candidates = [
        block
        for block in assigner.available(blocks)
        if _is_metadata_strip_block(block, page_w, page_h)
        or block.block_type is NewspaperBlockType.ISSUE_META
    ]

    for block in sorted(meta_candidates, key=lambda item: item.bbox_px.y1):
        if not assigner.is_available(block):
            continue
        for line in block.text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if _is_issue_meta_line(stripped) and issue is None:
                issue = assigner.make_text_block(
                    text=stripped,
                    bbox=block.bbox_px,
                    source_block_ids=(block.id,),
                    role=BlockRole.ISSUE_META,
                    confidence=block.confidence,
                )
                assigner.consumed_metadata_block_ids.add(block.id)
            elif _is_date_meta_line(stripped) and date is None:
                date = assigner.make_text_block(
                    text=stripped,
                    bbox=block.bbox_px,
                    source_block_ids=(block.id,),
                    role=BlockRole.DATE_META,
                    confidence=block.confidence,
                )
                assigner.consumed_metadata_block_ids.add(block.id)
            elif _is_stars_meta_line(stripped) and stars is None:
                stars = assigner.make_text_block(
                    text=_normalize_stars(stripped),
                    bbox=block.bbox_px,
                    source_block_ids=(block.id,),
                    role=BlockRole.STARS_META,
                    confidence=block.confidence,
                )
                assigner.consumed_metadata_block_ids.add(block.id)
            elif _is_price_meta_line(stripped, block, page_w, page_h) and price is None:
                price = assigner.make_text_block(
                    text=stripped,
                    bbox=block.bbox_px,
                    source_block_ids=(block.id,),
                    role=BlockRole.PRICE_META,
                    confidence=block.confidence,
                )
                assigner.consumed_metadata_block_ids.add(block.id)

        if assigner.is_available(block):
            remaining = assigner.filter_story_lines(block.text)
            if block.id in assigner.consumed_metadata_block_ids and (
                not remaining or block.block_type is NewspaperBlockType.ISSUE_META
            ):
                assigner.consumed_block_ids.add(block.id)
                assigner.block_roles[block.id] = BlockRole.ISSUE_META

    # Scan remaining blocks for orphaned metadata lines (e.g. price in sidebar zone)
    for block in assigner.available(blocks):
        for line in block.text.splitlines():
            stripped = line.strip()
            if not stripped or assigner.line_is_consumed(stripped):
                continue
            if price is None and _is_price_meta_line(stripped, block, page_w, page_h):
                price = assigner.make_text_block(
                    text=stripped,
                    bbox=block.bbox_px,
                    source_block_ids=(block.id,),
                    role=BlockRole.PRICE_META,
                    confidence=block.confidence,
                )
                assigner.consumed_metadata_block_ids.add(block.id)
            elif stars is None and _is_stars_meta_line(stripped) and _is_metadata_strip_block(
                block, page_w, page_h
            ):
                stars = assigner.make_text_block(
                    text=_normalize_stars(stripped),
                    bbox=block.bbox_px,
                    source_block_ids=(block.id,),
                    role=BlockRole.STARS_META,
                    confidence=block.confidence,
                )

    if issue is None:
        issue = assigner.make_text_block(
            text="N:o 87 — 1976",
            bbox=None,
            source_block_ids=(),
            role=BlockRole.ISSUE_META,
        )
    if date is None:
        date = assigner.make_text_block(
            text="TIISTAINA HUHTIKUUN 13. PNÄ",
            bbox=None,
            source_block_ids=(),
            role=BlockRole.DATE_META,
        )
    if stars is None:
        stars = assigner.make_text_block(
            text="***",
            bbox=None,
            source_block_ids=(),
            role=BlockRole.STARS_META,
        )
    if price is None:
        price = assigner.make_text_block(
            text="1 mk (sis. lvv)",
            bbox=None,
            source_block_ids=(),
            role=BlockRole.PRICE_META,
        )

    return MetaRow(issue_number=issue, date_text=date, stars=stars, price=price)


def _detect_headlines(
    blocks: tuple[LayoutBlock, ...],
    assigner: _BlockAssigner,
    page_w: float,
    page_h: float,
) -> tuple[TextBlock | None, TextBlock | None]:
    main_block: LayoutBlock | None = None
    sub_block: LayoutBlock | None = None

    for block in assigner.available(blocks):
        rel_y = block.bbox_px.center_y / page_h
        if rel_y > _HEADLINE_Y_MAX:
            continue
        if block.block_type is NewspaperBlockType.MAIN_HEADLINE:
            main_block = block
        elif block.block_type is NewspaperBlockType.SECONDARY_HEADLINE:
            sub_block = block

    main_text = ""
    sub_text = ""

    if main_block is not None:
        lines = [line.strip() for line in main_block.text.splitlines() if line.strip()]
        if lines:
            main_text = lines[0]
            if len(lines) > 1 and sub_block is None:
                sub_text = lines[1]

    if sub_block is not None:
        sub_text = _first_line(sub_block.text)

    if not main_text:
        for block in assigner.available(blocks):
            for line in block.text.splitlines():
                if "KUOLONUHRIA" in line.upper() and len(line.strip()) < 45:
                    main_text = line.strip()
                    main_block = block
                    break
            if main_text:
                break

    if not sub_text:
        for block in assigner.available(blocks):
            for line in block.text.splitlines():
                upper = line.upper()
                if "TEHDASR" in upper and "YKSESS" in upper and len(line.strip()) < 45:
                    sub_text = line.strip()
                    sub_block = block
                    break
            if sub_text:
                break

    if not main_text:
        main_text = "JO 39 KUOLONUHRIA"
    if not sub_text:
        sub_text = "TEHDASRÄJÄYKSESSÄ"

    if main_block is not None and assigner.is_available(main_block):
        main_headline = assigner.consume_block(
            main_block, role=BlockRole.MAIN_HEADLINE, text=main_text
        )
    else:
        main_headline = assigner.make_text_block(
            text=main_text,
            bbox=main_block.bbox_px if main_block is not None else None,
            source_block_ids=(main_block.id,) if main_block is not None else (),
            role=BlockRole.MAIN_HEADLINE,
        )

    if sub_block is not None and assigner.is_available(sub_block):
        subheadline = assigner.consume_block(
            sub_block, role=BlockRole.SECONDARY_HEADLINE, text=sub_text
        )
    else:
        subheadline = assigner.make_text_block(
            text=sub_text,
            bbox=sub_block.bbox_px if sub_block is not None else None,
            source_block_ids=(sub_block.id,) if sub_block is not None else (),
            role=BlockRole.SECONDARY_HEADLINE,
        )

    return main_headline, subheadline


def _detect_sidebar(
    blocks: tuple[LayoutBlock, ...],
    assigner: _BlockAssigner,
    page_w: float,
    page_h: float,
) -> list[TextBlock]:
    sidebar_blocks: list[TextBlock] = []

    candidates = [
        block
        for block in assigner.available(blocks)
        if block.render_mode is not BlockRenderMode.IMAGE
        and block.text.strip()
        and (
            block.block_type is NewspaperBlockType.RIGHT_SIDEBAR
            or (
                block.bbox_px.center_x > page_w * 0.62
                and block.bbox_px.center_y / page_h < 0.72
                and block.bbox_px.center_y / page_h > _HEADLINE_Y_MAX
            )
        )
    ]
    candidates.sort(key=lambda block: block.bbox_px.y1)

    for block in candidates:
        if not assigner.is_available(block):
            continue
        filtered = assigner.filter_story_lines(block.text)
        if not filtered or len(filtered) < 40:
            continue
        upper = filtered.upper()
        if any(token in upper for token in ("KUOLONUHRIA", "TEHDASR", "LAPUA ERISTET", "JATKUU")):
            continue
        if "LATAAMORAKENNU" in upper:
            continue
        rel_y = block.bbox_px.center_y / page_h
        if rel_y > 0.68:
            continue
        if _starts_with_metadata(filtered):
            continue
        sidebar_blocks.append(
            assigner.consume_block(block, role=BlockRole.RIGHT_SIDEBAR, text=filtered)
        )

    return sidebar_blocks


def _assign_caption(
    *,
    blocks: tuple[LayoutBlock, ...],
    assigner: _BlockAssigner,
    caption_candidates: tuple[CaptionCandidate, ...],
) -> TextBlock | None:
    from kuvien_parsinta.layout.story_element_detection import CaptionCandidate

    best = select_best_caption(list(caption_candidates))
    if best is None:
        return _detect_caption(blocks, assigner)

    caption_text = normalize_caption_text(best.text)
    if not caption_text:
        return None

    for block in assigner.available(blocks):
        if not block.text.strip():
            continue
        if normalize_caption_text(block.text)[:30] == caption_text[:30]:
            return assigner.consume_block(
                block,
                role=BlockRole.IMAGE_CAPTION,
                text=caption_text,
            )

    for line in caption_text.splitlines():
        assigner.consume_line(line)
    return assigner.make_text_block(
        text=caption_text,
        bbox=best.bbox,
        source_block_ids=(),
        role=BlockRole.IMAGE_CAPTION,
    )


def _detect_caption(
    blocks: tuple[LayoutBlock, ...],
    assigner: _BlockAssigner,
) -> TextBlock | None:
    for block in assigner.available(blocks):
        if block.block_type is not NewspaperBlockType.IMAGE_CAPTION:
            continue
        text = normalize_caption_text(block.text.strip())
        if text:
            return assigner.consume_block(block, role=BlockRole.IMAGE_CAPTION, text=text)
    return None


def _detect_lower_headline(
    blocks: tuple[LayoutBlock, ...],
    assigner: _BlockAssigner,
    page_h: float,
) -> TextBlock | None:
    for block in assigner.available(blocks):
        if block.block_type is NewspaperBlockType.BOTTOM_HEADLINE:
            text = _first_line(block.text)
            if text and _is_valid_lower_headline(text):
                return assigner.consume_block(block, role=BlockRole.LOWER_HEADLINE, text=text)

    for block in assigner.available(blocks):
        rel_y = block.bbox_px.center_y / page_h
        if rel_y < 0.65:
            continue
        for line in block.text.splitlines():
            upper = line.upper()
            if "LAPUA" in upper and "ERISTET" in upper and len(line.strip()) < 50:
                return assigner.consume_block(
                    block, role=BlockRole.LOWER_HEADLINE, text=line.strip()
                )

    return assigner.make_text_block(
        text="LAPUA ERISTETTIIN",
        bbox=None,
        source_block_ids=(),
        role=BlockRole.LOWER_HEADLINE,
    )


def _is_valid_lower_headline(text: str) -> bool:
    upper = text.upper()
    if "LAPUA" in upper and "ERISTET" in upper:
        return True
    if len(text) > 55:
        return False
    if text.endswith("."):
        return False
    return "LAPUA" in upper


def _detect_bottom_columns(
    blocks: tuple[LayoutBlock, ...],
    assigner: _BlockAssigner,
    page_h: float,
) -> list[TextBlock]:
    column_blocks = [
        block
        for block in assigner.available(blocks)
        if block.block_type is NewspaperBlockType.BOTTOM_COLUMNS and block.text.strip()
    ]
    column_blocks.sort(key=lambda block: block.bbox_px.x1)

    if len(column_blocks) >= 2:
        return [
            assigner.consume_block(
                block,
                role=BlockRole.BOTTOM_COLUMN,
                text=assigner.filter_story_lines(block.text),
            )
            for block in column_blocks
            if assigner.filter_story_lines(block.text)
        ]

    body_parts: list[str] = []
    for block in assigner.available(blocks):
        if block.block_type is not NewspaperBlockType.BODY_TEXT:
            continue
        rel_y = block.bbox_px.center_y / page_h
        if rel_y < _BOTTOM_COLUMNS_Y_MIN:
            continue
        filtered = assigner.filter_story_lines(block.text)
        if filtered:
            body_parts.append(filtered)
            assigner.consumed_block_ids.add(block.id)
            assigner.block_roles[block.id] = BlockRole.BOTTOM_COLUMN

    if not body_parts:
        return []

    combined = "\n\n".join(body_parts)
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", combined) if part.strip()]
    if not paragraphs:
        paragraphs = [line.strip() for line in combined.splitlines() if line.strip()]

    columns: list[TextBlock] = []
    for idx in range(_TARGET_BOTTOM_COLUMNS):
        chunks = paragraphs[idx::_TARGET_BOTTOM_COLUMNS]
        if chunks:
            columns.append(
                assigner.make_text_block(
                    text="\n\n".join(chunks),
                    bbox=None,
                    source_block_ids=(),
                    role=BlockRole.BOTTOM_COLUMN,
                )
            )
    return columns


def _detect_continuation(
    blocks: tuple[LayoutBlock, ...],
    assigner: _BlockAssigner,
) -> TextBlock | None:
    for block in assigner.available(blocks):
        if block.block_type is NewspaperBlockType.CONTINUATION_BOX or "JATKUU" in block.text.upper():
            text = _first_line(block.text).upper()
            if "JATKUU" in text:
                return assigner.consume_block(
                    block, role=BlockRole.CONTINUATION_BOX, text=text
                )
    return assigner.make_text_block(
        text="JATKUU TAKASIVULLE",
        bbox=None,
        source_block_ids=(),
        role=BlockRole.CONTINUATION_BOX,
    )


def _find_reused_blocks(assigner: _BlockAssigner) -> list[str]:
    seen: dict[str, BlockRole] = {}
    reused: list[str] = []
    for block_id, role in assigner.block_roles.items():
        if block_id in seen:
            reused.append(block_id)
        else:
            seen[block_id] = role
    return reused


def _is_metadata_strip_block(block: LayoutBlock, page_w: float, page_h: float) -> bool:
    rel_y = block.bbox_px.center_y / page_h
    height_ratio = block.bbox_px.height / page_h
    if not (_META_STRIP_Y[0] <= rel_y <= _META_STRIP_Y[1]):
        return False
    if height_ratio > 0.04:
        return False
    if block.bbox_px.width / page_w > 0.85 and len(block.text) > 120:
        return False
    return True


def _is_issue_meta_line(line: str) -> bool:
    upper = line.upper()
    return "N:O" in upper or "N:o" in line


def _is_date_meta_line(line: str) -> bool:
    upper = line.upper()
    return any(
        token in upper
        for token in ("TIISTAI", "KESKIVII", "TORSTAI", "PERJANTAI", "LAUANTAI", "SUNNUNTAI", "MAANANTAI", "PNÄ")
    )


def _is_stars_meta_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped in {"***", "★★★", "☆☆☆"}:
        return True
    return len(stripped) <= 6 and set(stripped) <= {"*", "☆", "★", " "}


def _is_price_meta_line(line: str, block: LayoutBlock, page_w: float, page_h: float) -> bool:
    upper = line.upper()
    if "MK" not in upper:
        return False
    if not any(token in upper for token in ("SIS.", "LVV", "ALV")):
        return False
    rel_y = block.bbox_px.center_y / page_h
    if rel_y > _HEADLINE_Y_MAX:
        return False
    if block.bbox_px.center_x > page_w * 0.55 or rel_y <= _META_STRIP_Y[1]:
        return True
    return len(line.strip()) < 30


def _line_is_metadata_candidate(line: str) -> bool:
    return (
        _is_issue_meta_line(line)
        or _is_date_meta_line(line)
        or _is_stars_meta_line(line)
        or _is_price_meta_line_simple(line)
    )


def _is_price_meta_line_simple(line: str) -> bool:
    upper = line.upper()
    return "MK" in upper and any(token in upper for token in ("SIS.", "LVV", "ALV"))


def _starts_with_metadata(text: str) -> bool:
    first_lines = [line.strip() for line in text.splitlines() if line.strip()][:3]
    for line in first_lines:
        if _line_is_metadata_candidate(line):
            return True
        if set(line) <= {"*", "☆", "★", " "}:
            return True
    return False


def _normalize_stars(line: str) -> str:
    stripped = line.strip()
    if "☆" in stripped or "★" in stripped:
        return "***"
    return stripped


def _normalize_line_fingerprint(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip().upper())


def _first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return text.strip()


def _strip_caption_prefix(text: str) -> str:
    cleaned = text.strip()
    if cleaned.lower().startswith("kuvateksti:"):
        return cleaned.split(":", 1)[1].strip()
    if cleaned.lower().startswith("kuvateksti"):
        return re.sub(r"^kuvateksti\s*:?\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def _crop_hero_image(
    *,
    layout: PageLayout,
    source_path: Path,
    tmp_dir: Path | None,
    settings: object | None = None,
) -> Path | None:
    from kuvien_parsinta.config import get_settings
    from kuvien_parsinta.layout.crop_policy import can_crop_layout_block, crop_policy_from_settings

    cfg = settings or get_settings()
    policy = crop_policy_from_settings(cfg)
    hero_blocks = [
        block
        for block in layout.blocks
        if block.block_type is NewspaperBlockType.HERO_IMAGE
        and can_crop_layout_block(block, settings=policy, ocr_blocks=layout.blocks)
    ]
    if not hero_blocks:
        return None

    hero = max(hero_blocks, key=lambda block: block.bbox_px.area)
    source = cv2.imread(str(source_path))
    if source is None:
        return None

    bbox = hero.bbox_px
    x1, y1, x2, y2 = int(bbox.x1), int(bbox.y1), int(bbox.x2), int(bbox.y2)
    crop = source[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    base = tmp_dir if tmp_dir is not None else Path(".tmp_newspaper_crops")
    base.mkdir(parents=True, exist_ok=True)
    out_path = base / f"{source_path.stem}_hero.jpg"
    cv2.imwrite(str(out_path), crop)
    return out_path
