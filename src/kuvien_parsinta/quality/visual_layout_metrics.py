"""Visual layout metrics for newspaper structural PDF quality gate."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from kuvien_parsinta.layout.source_anchors import RenderBox, SourceAnchoredLayout


@dataclass
class VisualLayoutMetrics:
    masthead_overlap: bool
    vertical_whitespace_ratio: float
    headline_to_image_gap_ratio: float
    image_to_caption_gap_ratio: float
    caption_to_lower_headline_gap_ratio: float
    lower_headline_to_columns_gap_ratio: float
    hero_image_width_ratio: float
    right_sidebar_width_ratio: float
    bottom_column_font_size: float
    masthead_render_mode: str
    text_crops_used: bool = False
    photo_crops_used: bool = False
    forbidden_text_crop_blocks: list[str] = field(default_factory=list)
    newspaper_name_render_mode: str = "text"
    headlines_render_mode: str = "text"
    metadata_render_mode: str = "text"
    caption_render_mode: str = "text"
    continuation_text_render_mode: str = "text"
    warnings: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, object]:
        return {
            "masthead_overlap": self.masthead_overlap,
            "vertical_whitespace_ratio": round(self.vertical_whitespace_ratio, 4),
            "total_vertical_whitespace_ratio": round(self.vertical_whitespace_ratio, 4),
            "headline_to_image_gap_ratio": round(self.headline_to_image_gap_ratio, 4),
            "headline_to_hero_gap_ratio": round(self.headline_to_image_gap_ratio, 4),
            "image_to_caption_gap_ratio": round(self.image_to_caption_gap_ratio, 4),
            "hero_to_caption_gap_ratio": round(self.image_to_caption_gap_ratio, 4),
            "caption_to_lower_headline_gap_ratio": round(
                self.caption_to_lower_headline_gap_ratio, 4
            ),
            "lower_headline_to_columns_gap_ratio": round(
                self.lower_headline_to_columns_gap_ratio, 4
            ),
            "hero_image_width_ratio": round(self.hero_image_width_ratio, 4),
            "right_sidebar_width_ratio": round(self.right_sidebar_width_ratio, 4),
            "bottom_column_font_size": round(self.bottom_column_font_size, 2),
            "masthead_render_mode": self.masthead_render_mode,
            "text_crops_used": self.text_crops_used,
            "photo_crops_used": self.photo_crops_used,
            "forbidden_text_crop_blocks": self.forbidden_text_crop_blocks,
            "newspaper_name_render_mode": self.newspaper_name_render_mode,
            "headlines_render_mode": self.headlines_render_mode,
            "metadata_render_mode": self.metadata_render_mode,
            "caption_render_mode": self.caption_render_mode,
            "continuation_text_render_mode": self.continuation_text_render_mode,
            "warnings": self.warnings,
        }


def build_visual_layout_metrics(
    *,
    layout_boxes: SourceAnchoredLayout,
    page_h_pt: float,
    page_w_pt: float,
    masthead_render_mode: str,
    masthead_overlap: bool,
    bottom_column_font_size: float,
    placed: dict[str, RenderBox],
    text_crops_used: bool = False,
    photo_crops_used: bool = False,
    forbidden_text_crop_blocks: list[str] | None = None,
    newspaper_name_render_mode: str = "text",
    headlines_render_mode: str = "text",
    metadata_render_mode: str = "text",
    caption_render_mode: str = "text",
    continuation_text_render_mode: str = "text",
) -> VisualLayoutMetrics:
    content_h = page_h_pt - 2 * layout_boxes.margin
    used_bottom = max(box.bottom for box in placed.values())
    whitespace = max(0.0, content_h - (used_bottom - layout_boxes.margin))
    vertical_whitespace_ratio = whitespace / content_h if content_h > 0 else 0.0

    headline_bottom = placed.get("headline_group", layout_boxes.headline_group).bottom
    hero_top = placed.get("hero_image", layout_boxes.hero_image).y
    caption_top = placed.get("caption", layout_boxes.caption).y
    hero_bottom = placed.get("hero_image", layout_boxes.hero_image).bottom
    lower_top = placed.get("lower_headline", layout_boxes.lower_headline).y
    lower_bottom = placed.get("lower_headline", layout_boxes.lower_headline).bottom
    columns_top = placed.get("bottom_columns", layout_boxes.bottom_columns).y

    warnings: list[str] = []
    headline_gap = (hero_top - headline_bottom) / page_h_pt
    caption_gap = (caption_top - hero_bottom) / page_h_pt
    lower_gap = (lower_top - placed.get("caption", layout_boxes.caption).bottom) / page_h_pt
    columns_gap = (columns_top - lower_bottom) / page_h_pt

    if headline_gap > 0.045:
        warnings.append("headline_to_hero_gap_too_large")
    if caption_gap > 0.022:
        warnings.append("hero_to_caption_gap_too_large")
    if lower_gap > 0.035:
        warnings.append("caption_to_lower_headline_gap_too_large")
    if columns_gap > 0.025:
        warnings.append("lower_headline_to_columns_gap_too_large")
    if vertical_whitespace_ratio > 0.15:
        warnings.append("total_vertical_whitespace_too_high")
    if masthead_overlap:
        warnings.append("masthead_overlap_detected")
    if bottom_column_font_size < 5.5:
        warnings.append("bottom_column_font_size_below_minimum")
    if layout_boxes.hero_width_ratio < 0.70:
        warnings.append("hero_image_too_narrow")
    if layout_boxes.sidebar_width_ratio < 0.18:
        warnings.append("sidebar_too_narrow")

    return VisualLayoutMetrics(
        masthead_overlap=masthead_overlap,
        vertical_whitespace_ratio=vertical_whitespace_ratio,
        headline_to_image_gap_ratio=headline_gap,
        image_to_caption_gap_ratio=caption_gap,
        caption_to_lower_headline_gap_ratio=lower_gap,
        lower_headline_to_columns_gap_ratio=columns_gap,
        hero_image_width_ratio=layout_boxes.hero_width_ratio,
        right_sidebar_width_ratio=layout_boxes.sidebar_width_ratio,
        bottom_column_font_size=bottom_column_font_size,
        masthead_render_mode=masthead_render_mode,
        text_crops_used=text_crops_used,
        photo_crops_used=photo_crops_used,
        forbidden_text_crop_blocks=forbidden_text_crop_blocks or [],
        newspaper_name_render_mode=newspaper_name_render_mode,
        headlines_render_mode=headlines_render_mode,
        metadata_render_mode=metadata_render_mode,
        caption_render_mode=caption_render_mode,
        continuation_text_render_mode=continuation_text_render_mode,
        warnings=warnings,
    )


def save_visual_metrics(*, metrics: VisualLayoutMetrics, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(metrics.to_json_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path
