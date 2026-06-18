"""Source-anchored layout boxes derived from OCR/structure bboxes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from kuvien_parsinta.layout.newspaper_page_model import NewspaperFrontPageModel
from kuvien_parsinta.layout.page_layout import BboxPx, LayoutBlock, NewspaperBlockType, PageLayout


@dataclass(frozen=True, slots=True)
class RelativeBox:
    """Normalized box in source image coordinates (origin top-left, 0-1)."""

    x: float
    y: float
    width: float
    height: float

    @property
    def x2(self) -> float:
        return self.x + self.width

    @property
    def y2(self) -> float:
        return self.y + self.height

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2


@dataclass(frozen=True, slots=True)
class SourceAnchors:
    masthead_box: RelativeBox | None
    meta_row_box: RelativeBox | None
    headline_group_box: RelativeBox | None
    hero_image_box: RelativeBox | None
    right_sidebar_box: RelativeBox | None
    caption_box: RelativeBox | None
    lower_headline_box: RelativeBox | None
    bottom_columns_box: RelativeBox | None
    continuation_box: RelativeBox | None


@dataclass(frozen=True, slots=True)
class CompactSpacing:
    newspaper_compact: bool
    vertical_gap_scale: float
    headline_to_image_gap_ratio: float
    image_to_caption_gap_ratio: float
    caption_to_lower_headline_gap_ratio: float
    lower_headline_to_columns_gap_ratio: float
    margin_ratio: float


@dataclass(frozen=True, slots=True)
class RenderBox:
    x: float
    y: float
    width: float
    height: float

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True, slots=True)
class SourceAnchoredLayout:
    masthead: RenderBox
    meta_row: RenderBox
    headline_group: RenderBox
    hero_image: RenderBox
    right_sidebar: RenderBox
    caption: RenderBox
    lower_headline: RenderBox
    bottom_columns: RenderBox
    continuation: RenderBox
    content_width: float
    margin: float
    hero_width_ratio: float
    sidebar_width_ratio: float


def build_source_anchors(
    *,
    layout: PageLayout,
    model: NewspaperFrontPageModel,
) -> SourceAnchors:
    page_w = float(layout.page_width_px)
    page_h = float(layout.page_height_px)

    def to_rel(bbox: BboxPx) -> RelativeBox:
        return RelativeBox(
            x=bbox.x1 / page_w,
            y=bbox.y1 / page_h,
            width=bbox.width / page_w,
            height=bbox.height / page_h,
        )

    def union_blocks(
        blocks: tuple[LayoutBlock, ...],
        *,
        fallback: RelativeBox | None = None,
    ) -> RelativeBox | None:
        if not blocks:
            return fallback
        x1 = min(block.bbox_px.x1 for block in blocks)
        y1 = min(block.bbox_px.y1 for block in blocks)
        x2 = max(block.bbox_px.x2 for block in blocks)
        y2 = max(block.bbox_px.y2 for block in blocks)
        return to_rel(BboxPx(x1, y1, x2, y2))

    masthead_blocks = _blocks_of_types(
        layout.blocks,
        NewspaperBlockType.MASTHEAD_LOGO,
        NewspaperBlockType.NEWSPAPER_NAME,
    )
    masthead_blocks = tuple(
        block for block in masthead_blocks if block.bbox_px.y2 / page_h <= 0.16
    )
    masthead = union_blocks(
        masthead_blocks,
        fallback=RelativeBox(x=0.04, y=0.02, width=0.92, height=0.11),
    )

    meta_blocks = _blocks_of_types(layout.blocks, NewspaperBlockType.ISSUE_META)
    meta = union_blocks(
        meta_blocks,
        fallback=RelativeBox(x=0.04, y=0.13, width=0.92, height=0.035),
    )

    headline_blocks = _blocks_of_types(
        layout.blocks,
        NewspaperBlockType.MAIN_HEADLINE,
        NewspaperBlockType.SECONDARY_HEADLINE,
    )
    headline = union_blocks(
        headline_blocks,
        fallback=RelativeBox(x=0.04, y=0.17, width=0.92, height=0.14),
    )

    hero_blocks = _blocks_of_types(layout.blocks, NewspaperBlockType.HERO_IMAGE)
    hero = union_blocks(
        hero_blocks,
        fallback=RelativeBox(x=0.04, y=0.33, width=0.58, height=0.36),
    )

    sidebar_blocks = _blocks_of_types(layout.blocks, NewspaperBlockType.RIGHT_SIDEBAR)
    sidebar = union_blocks(
        sidebar_blocks,
        fallback=RelativeBox(x=0.66, y=0.33, width=0.28, height=0.36),
    )

    caption_blocks = _blocks_of_types(layout.blocks, NewspaperBlockType.IMAGE_CAPTION)
    caption = union_blocks(caption_blocks)
    if caption is None and model.main_story.caption is not None and model.main_story.caption.bbox:
        caption = to_rel(model.main_story.caption.bbox)
    if caption is None and hero is not None:
        caption = RelativeBox(
            x=hero.x,
            y=hero.y2 + 0.004,
            width=hero.width,
            height=0.028,
        )

    lower_blocks = _blocks_of_types(layout.blocks, NewspaperBlockType.BOTTOM_HEADLINE)
    lower = union_blocks(
        lower_blocks,
        fallback=RelativeBox(x=0.04, y=0.72, width=0.92, height=0.05),
    )

    column_blocks = _blocks_of_types(layout.blocks, NewspaperBlockType.BOTTOM_COLUMNS)
    columns = union_blocks(
        column_blocks,
        fallback=RelativeBox(x=0.04, y=0.78, width=0.78, height=0.16),
    )

    cont_blocks = _blocks_of_types(layout.blocks, NewspaperBlockType.CONTINUATION_BOX)
    continuation = union_blocks(
        cont_blocks,
        fallback=RelativeBox(x=0.72, y=0.90, width=0.22, height=0.035),
    )

    return SourceAnchors(
        masthead_box=masthead,
        meta_row_box=meta,
        headline_group_box=headline,
        hero_image_box=hero,
        right_sidebar_box=sidebar,
        caption_box=caption,
        lower_headline_box=lower,
        bottom_columns_box=columns,
        continuation_box=continuation,
    )


def resolve_source_anchored_layout(
    *,
    anchors: SourceAnchors,
    page_w_pt: float,
    page_h_pt: float,
    spacing: CompactSpacing,
) -> SourceAnchoredLayout:
    margin = page_w_pt * spacing.margin_ratio
    content_w = page_w_pt - 2 * margin
    gap_scale = spacing.vertical_gap_scale if spacing.newspaper_compact else 1.0

    def gap(ratio: float) -> float:
        return page_h_pt * ratio * gap_scale

    def rel_height(box: RelativeBox | None, default_ratio: float, *, min_ratio: float) -> float:
        if box is None:
            return page_h_pt * default_ratio
        return max(page_h_pt * min_ratio, box.height * page_h_pt)

    def rel_x(box: RelativeBox | None, default_x: float) -> float:
        if box is None:
            return margin + content_w * default_x
        return margin + box.x * content_w / max(0.55, 1.0 - 2 * spacing.margin_ratio)

    y = margin * 0.6

    masthead_src = anchors.masthead_box or RelativeBox(0.04, 0.02, 0.92, 0.11)
    masthead_h = rel_height(masthead_src, 0.11, min_ratio=0.095)
    masthead = RenderBox(x=margin, y=y, width=content_w, height=masthead_h)
    y = masthead.bottom + gap(0.003)

    meta_src = anchors.meta_row_box or RelativeBox(0.04, 0.13, 0.92, 0.03)
    meta_h = rel_height(meta_src, 0.028, min_ratio=0.022)
    meta_row = RenderBox(x=margin, y=y, width=content_w, height=meta_h)
    y = meta_row.bottom + gap(0.003)

    headline_src = anchors.headline_group_box or RelativeBox(0.04, 0.17, 0.92, 0.12)
    headline_h = rel_height(headline_src, 0.12, min_ratio=0.09)
    headline_group = RenderBox(x=margin, y=y, width=content_w, height=headline_h)
    y = headline_group.bottom + gap(spacing.headline_to_image_gap_ratio)

    hero_src = anchors.hero_image_box or RelativeBox(0.04, 0.33, 0.58, 0.36)
    sidebar_src = anchors.right_sidebar_box or RelativeBox(0.66, 0.33, 0.28, 0.36)

    hero_w_ratio = _clamp(hero_src.width, 0.72, 0.78)
    sidebar_w_ratio = _clamp(sidebar_src.width, 0.18, 0.22)
    gutter = content_w * 0.012
    hero_w = content_w * hero_w_ratio
    sidebar_w = content_w * sidebar_w_ratio
    if hero_w + sidebar_w + gutter > content_w:
        scale = content_w / (hero_w + sidebar_w + gutter)
        hero_w *= scale
        sidebar_w *= scale
        hero_w_ratio = hero_w / content_w
        sidebar_w_ratio = sidebar_w / content_w

    hero_h = rel_height(hero_src, 0.34, min_ratio=0.28)
    hero_image = RenderBox(x=margin, y=y, width=hero_w, height=hero_h)
    right_sidebar = RenderBox(
        x=margin + hero_w + gutter,
        y=y,
        width=sidebar_w,
        height=hero_h,
    )
    y = hero_image.bottom + gap(spacing.image_to_caption_gap_ratio)

    caption_src = anchors.caption_box or RelativeBox(hero_src.x, hero_src.y2, hero_src.width, 0.025)
    caption_h = rel_height(caption_src, 0.028, min_ratio=0.022)
    caption = RenderBox(x=hero_image.x, y=y, width=hero_image.width, height=caption_h)
    y = caption.bottom + gap(spacing.caption_to_lower_headline_gap_ratio)

    lower_src = anchors.lower_headline_box or RelativeBox(0.04, 0.72, 0.92, 0.045)
    lower_h = rel_height(lower_src, 0.042, min_ratio=0.032)
    lower_headline = RenderBox(x=margin, y=y, width=content_w, height=lower_h)
    y = lower_headline.bottom + gap(spacing.lower_headline_to_columns_gap_ratio)

    columns_src = anchors.bottom_columns_box or RelativeBox(0.04, 0.78, 0.78, 0.14)
    columns_h = rel_height(columns_src, 0.13, min_ratio=0.10)
    columns_y = max(y, columns_src.y * page_h_pt * 0.98)
    bottom_columns = RenderBox(x=margin, y=columns_y, width=content_w * 0.78, height=columns_h)

    cont_src = anchors.continuation_box or RelativeBox(0.72, 0.90, 0.22, 0.035)
    cont_w = content_w * _clamp(cont_src.width, 0.20, 0.26)
    cont_h = rel_height(cont_src, 0.034, min_ratio=0.028)
    continuation = RenderBox(
        x=page_w_pt - margin - cont_w,
        y=bottom_columns.y + bottom_columns.height - cont_h,
        width=cont_w,
        height=cont_h,
    )

    layout = SourceAnchoredLayout(
        masthead=masthead,
        meta_row=meta_row,
        headline_group=headline_group,
        hero_image=hero_image,
        right_sidebar=right_sidebar,
        caption=caption,
        lower_headline=lower_headline,
        bottom_columns=bottom_columns,
        continuation=continuation,
        content_width=content_w,
        margin=margin,
        hero_width_ratio=hero_w_ratio,
        sidebar_width_ratio=sidebar_w_ratio,
    )
    return _fit_layout_to_page(layout, page_h_pt=page_h_pt)


def _fit_layout_to_page(layout: SourceAnchoredLayout, *, page_h_pt: float) -> SourceAnchoredLayout:
    max_bottom = max(
        layout.bottom_columns.bottom,
        layout.continuation.bottom,
        layout.lower_headline.bottom,
    )
    limit = page_h_pt * 0.965
    if max_bottom <= limit:
        return layout

    scale = limit / max_bottom
    origin = layout.margin * 0.5

    def scale_box(box: RenderBox) -> RenderBox:
        return RenderBox(
            x=box.x,
            y=origin + (box.y - origin) * scale,
            width=box.width,
            height=box.height * scale,
        )

    return SourceAnchoredLayout(
        masthead=scale_box(layout.masthead),
        meta_row=scale_box(layout.meta_row),
        headline_group=scale_box(layout.headline_group),
        hero_image=scale_box(layout.hero_image),
        right_sidebar=RenderBox(
            x=layout.right_sidebar.x,
            y=origin + (layout.hero_image.y - origin) * scale,
            width=layout.right_sidebar.width,
            height=layout.hero_image.height * scale,
        ),
        caption=scale_box(layout.caption),
        lower_headline=scale_box(layout.lower_headline),
        bottom_columns=scale_box(layout.bottom_columns),
        continuation=scale_box(layout.continuation),
        content_width=layout.content_width,
        margin=layout.margin,
        hero_width_ratio=layout.hero_width_ratio,
        sidebar_width_ratio=layout.sidebar_width_ratio,
    )


def _blocks_of_types(
    blocks: tuple[LayoutBlock, ...],
    *types: NewspaperBlockType,
) -> tuple[LayoutBlock, ...]:
    allowed = set(types)
    return tuple(block for block in blocks if block.block_type in allowed)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
