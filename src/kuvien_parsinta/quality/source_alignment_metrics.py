"""Compare rendered layout ratios against source image anchor ratios."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from kuvien_parsinta.layout.source_anchors import RenderBox, SourceAnchors, SourceAnchoredLayout


@dataclass(frozen=True, slots=True)
class SourceAlignmentMetrics:
    masthead_height_ratio_source: float
    masthead_height_ratio_rendered: float
    headline_group_height_ratio_source: float
    headline_group_height_ratio_rendered: float
    hero_width_ratio_source: float
    hero_width_ratio_rendered: float
    hero_height_ratio_source: float
    hero_height_ratio_rendered: float
    sidebar_width_ratio_source: float
    sidebar_width_ratio_rendered: float
    caption_y_ratio_source: float
    caption_y_ratio_rendered: float
    lower_headline_y_ratio_source: float
    lower_headline_y_ratio_rendered: float
    bottom_columns_y_ratio_source: float
    bottom_columns_y_ratio_rendered: float
    warnings: tuple[str, ...]

    def to_json_dict(self) -> dict[str, object]:
        return {
            "masthead_height_ratio_source": round(self.masthead_height_ratio_source, 4),
            "masthead_height_ratio_rendered": round(self.masthead_height_ratio_rendered, 4),
            "headline_group_height_ratio_source": round(self.headline_group_height_ratio_source, 4),
            "headline_group_height_ratio_rendered": round(self.headline_group_height_ratio_rendered, 4),
            "hero_width_ratio_source": round(self.hero_width_ratio_source, 4),
            "hero_width_ratio_rendered": round(self.hero_width_ratio_rendered, 4),
            "hero_height_ratio_source": round(self.hero_height_ratio_source, 4),
            "hero_height_ratio_rendered": round(self.hero_height_ratio_rendered, 4),
            "sidebar_width_ratio_source": round(self.sidebar_width_ratio_source, 4),
            "sidebar_width_ratio_rendered": round(self.sidebar_width_ratio_rendered, 4),
            "caption_y_ratio_source": round(self.caption_y_ratio_source, 4),
            "caption_y_ratio_rendered": round(self.caption_y_ratio_rendered, 4),
            "lower_headline_y_ratio_source": round(self.lower_headline_y_ratio_source, 4),
            "lower_headline_y_ratio_rendered": round(self.lower_headline_y_ratio_rendered, 4),
            "bottom_columns_y_ratio_source": round(self.bottom_columns_y_ratio_source, 4),
            "bottom_columns_y_ratio_rendered": round(self.bottom_columns_y_ratio_rendered, 4),
            "warnings": list(self.warnings),
        }


def build_source_alignment_metrics(
    *,
    anchors: SourceAnchors,
    layout: SourceAnchoredLayout,
    page_h_pt: float,
    page_w_pt: float,
    placed: dict[str, RenderBox],
) -> SourceAlignmentMetrics:
    def rel_h(box: RenderBox) -> float:
        return box.height / page_h_pt if page_h_pt > 0 else 0.0

    def rel_y(box: RenderBox) -> float:
        return box.y / page_h_pt if page_h_pt > 0 else 0.0

    def rel_w(box: RenderBox, content_w: float) -> float:
        return box.width / content_w if content_w > 0 else 0.0

    content_w = layout.content_width
    masthead_src = anchors.masthead_box
    headline_src = anchors.headline_group_box
    hero_src = anchors.hero_image_box
    sidebar_src = anchors.right_sidebar_box
    caption_src = anchors.caption_box
    lower_src = anchors.lower_headline_box
    columns_src = anchors.bottom_columns_box

    masthead = placed.get("masthead", layout.masthead)
    headline = placed.get("headline_group", layout.headline_group)
    hero = placed.get("hero_image", layout.hero_image)
    sidebar = placed.get("right_sidebar", layout.right_sidebar)
    caption = placed.get("caption", layout.caption)
    lower = placed.get("lower_headline", layout.lower_headline)
    columns = placed.get("bottom_columns", layout.bottom_columns)

    warnings: list[str] = []
    pairs = (
        ("masthead_height", masthead_src.height if masthead_src else 0.1, rel_h(masthead), 0.08),
        ("headline_height", headline_src.height if headline_src else 0.12, rel_h(headline), 0.10),
        ("hero_width", hero_src.width if hero_src else 0.58, rel_w(hero, content_w), 0.12),
        ("hero_height", hero_src.height if hero_src else 0.34, rel_h(hero), 0.10),
        ("sidebar_width", sidebar_src.width if sidebar_src else 0.22, rel_w(sidebar, content_w), 0.08),
    )
    for name, src, rendered, tolerance in pairs:
        if abs(src - rendered) > tolerance:
            warnings.append(f"{name}_ratio_drift")

    return SourceAlignmentMetrics(
        masthead_height_ratio_source=masthead_src.height if masthead_src else 0.0,
        masthead_height_ratio_rendered=rel_h(masthead),
        headline_group_height_ratio_source=headline_src.height if headline_src else 0.0,
        headline_group_height_ratio_rendered=rel_h(headline),
        hero_width_ratio_source=hero_src.width if hero_src else 0.0,
        hero_width_ratio_rendered=rel_w(hero, content_w),
        hero_height_ratio_source=hero_src.height if hero_src else 0.0,
        hero_height_ratio_rendered=rel_h(hero),
        sidebar_width_ratio_source=sidebar_src.width if sidebar_src else 0.0,
        sidebar_width_ratio_rendered=rel_w(sidebar, content_w),
        caption_y_ratio_source=caption_src.y if caption_src else 0.0,
        caption_y_ratio_rendered=rel_y(caption),
        lower_headline_y_ratio_source=lower_src.y if lower_src else 0.0,
        lower_headline_y_ratio_rendered=rel_y(lower),
        bottom_columns_y_ratio_source=columns_src.y if columns_src else 0.0,
        bottom_columns_y_ratio_rendered=rel_y(columns),
        warnings=tuple(warnings),
    )


def save_source_alignment_metrics(*, metrics: SourceAlignmentMetrics, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(metrics.to_json_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path
