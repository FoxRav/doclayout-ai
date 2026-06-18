"""Typography roles and styles for newspaper structural PDF rendering."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal

from kuvien_parsinta.layout.newspaper_page_model import NewspaperFrontPageModel
from kuvien_parsinta.pdf.render import ACCENT, BODY_GRAY

MastheadRenderMode = Literal["text", "crop"]


class FontRole(str, Enum):
    MASTHEAD_LABEL = "masthead_label"
    NEWSPAPER_NAME = "newspaper_name"
    ISSUE_META = "issue_meta"
    MAIN_HEADLINE = "main_headline"
    SECONDARY_HEADLINE = "secondary_headline"
    HERO_SIDEBAR_BODY = "hero_sidebar_body"
    IMAGE_CAPTION = "image_caption"
    LOWER_HEADLINE = "lower_headline"
    BOTTOM_COLUMN_BODY = "bottom_column_body"
    CONTINUATION_BOX = "continuation_box"


@dataclass(frozen=True, slots=True)
class TypographyStyle:
    role: FontRole
    font_family_candidate: str
    fallback_font: str
    font_size: float
    font_weight: Literal["normal", "bold"]
    is_condensed: bool
    is_uppercase: bool
    color: tuple[int, int, int]
    alignment: Literal["L", "C", "R"]
    line_spacing: float
    letter_spacing: float
    max_width: float | None
    min_font_size: float
    max_font_size: float
    fpdf_family: str = "Ar"
    fpdf_style: str = ""


@dataclass(frozen=True, slots=True)
class MetaRowModel:
    issue_number: str
    date_text: str
    stars: str
    price: str
    bbox_source: tuple[float, float, float, float] | None
    confidence: float


@dataclass(frozen=True, slots=True)
class ImageCaptionModel:
    text: str
    bbox: tuple[float, float, float, float] | None
    related_image_id: str


@dataclass
class TypographyPlan:
    styles: dict[FontRole, TypographyStyle]
    meta_row: MetaRowModel
    caption: ImageCaptionModel | None
    masthead_render_mode: MastheadRenderMode
    headline_font_size: float
    secondary_headline_font_size: float
    body_font_size: float
    caption_font_size: float
    bottom_column_font_size: float
    lower_headline_font_size: float
    masthead_similarity_warning: bool = False
    warnings: list[str] = field(default_factory=list)
    overflow_warnings: list[str] = field(default_factory=list)

    def to_debug_dict(self) -> dict[str, object]:
        return {
            "font_roles": {
                role.value: {
                    "font_family_candidate": style.font_family_candidate,
                    "fallback_font": style.fallback_font,
                    "font_size": round(style.font_size, 2),
                    "font_weight": style.font_weight,
                    "is_condensed": style.is_condensed,
                    "is_uppercase": style.is_uppercase,
                    "color": list(style.color),
                    "alignment": style.alignment,
                    "line_spacing": style.line_spacing,
                    "fpdf_family": style.fpdf_family,
                    "fpdf_style": style.fpdf_style,
                }
                for role, style in self.styles.items()
            },
            "masthead_render_mode": self.masthead_render_mode,
            "headline_font_size": round(self.headline_font_size, 2),
            "secondary_headline_font_size": round(self.secondary_headline_font_size, 2),
            "body_font_size": round(self.body_font_size, 2),
            "caption_font_size": round(self.caption_font_size, 2),
            "bottom_column_font_size": round(self.bottom_column_font_size, 2),
            "lower_headline_font_size": round(self.lower_headline_font_size, 2),
            "meta_row": {
                "issue_number": self.meta_row.issue_number,
                "date_text": self.meta_row.date_text,
                "stars": self.meta_row.stars,
                "price": self.meta_row.price,
                "confidence": self.meta_row.confidence,
            },
            "caption": (
                {"text": self.caption.text, "related_image_id": self.caption.related_image_id}
                if self.caption is not None
                else None
            ),
            "warnings": self.warnings,
            "overflow_warnings": self.overflow_warnings,
            "masthead_similarity_warning": self.masthead_similarity_warning,
        }


@dataclass(frozen=True, slots=True)
class StructuralLayoutParams:
    margin_ratio: float
    compact_vertical: bool
    page_scale: Literal["standard", "large"]
    hero_width_ratio: float
    sidebar_width_ratio: float
    masthead_zone: tuple[float, float]
    meta_zone: tuple[float, float]
    headline_zone: tuple[float, float]
    middle_zone: tuple[float, float]
    caption_zone: tuple[float, float]
    bottom_headline_zone: tuple[float, float]
    bottom_columns_zone: tuple[float, float]


def resolve_layout_params(
    *,
    margin_ratio: float,
    compact_vertical: bool,
    page_scale: str,
) -> StructuralLayoutParams:
    scale_boost = 1.04 if page_scale == "large" else 1.0
    if compact_vertical:
        return StructuralLayoutParams(
            margin_ratio=margin_ratio,
            compact_vertical=True,
            page_scale="large" if page_scale == "large" else "standard",
            hero_width_ratio=0.74 * scale_boost,
            sidebar_width_ratio=0.20,
            masthead_zone=(0.025, 0.135),
            meta_zone=(0.138, 0.178),
            headline_zone=(0.185, 0.335),
            middle_zone=(0.345, 0.725),
            caption_zone=(0.728, 0.758),
            bottom_headline_zone=(0.765, 0.835),
            bottom_columns_zone=(0.845, 0.965),
        )
    return StructuralLayoutParams(
        margin_ratio=margin_ratio,
        compact_vertical=False,
        page_scale="large" if page_scale == "large" else "standard",
        hero_width_ratio=0.75,
        sidebar_width_ratio=0.20,
        masthead_zone=(0.03, 0.17),
        meta_zone=(0.18, 0.22),
        headline_zone=(0.23, 0.38),
        middle_zone=(0.39, 0.70),
        caption_zone=(0.70, 0.73),
        bottom_headline_zone=(0.74, 0.82),
        bottom_columns_zone=(0.83, 0.96),
    )


def build_typography_plan(
    *,
    model: NewspaperFrontPageModel,
    page_width_pt: float,
    page_height_pt: float,
    layout_params: StructuralLayoutParams,
    body_min_font_size: float,
    bottom_column_min_font_size: float,
    render_masthead_as_text: bool = True,
    allow_text_crops: bool = False,
    allow_overflow_report: bool,
) -> TypographyPlan:
    margin = page_width_pt * layout_params.margin_ratio
    content_w = page_width_pt - 2 * margin

    body_size = max(body_min_font_size, 7.0 if layout_params.compact_vertical else 6.5)
    caption_size = max(body_min_font_size - 0.5, 5.5)
    meta_size = max(body_min_font_size - 0.25, 6.0)
    columns_zone_h = (
        layout_params.bottom_columns_zone[1] - layout_params.bottom_columns_zone[0]
    ) * page_height_pt
    bottom_size = max(
        bottom_column_min_font_size,
        min(7.0, columns_zone_h / 24.0 if columns_zone_h > 0 else bottom_column_min_font_size),
    )

    masthead_zone_h = (layout_params.masthead_zone[1] - layout_params.masthead_zone[0]) * page_height_pt
    masthead_label_size = fit_text_to_box(
        text=model.masthead_text or "KUVA ERIKOIS",
        box_width=content_w,
        box_height=masthead_zone_h * 0.38,
        start_size=min(24.0, masthead_zone_h * 0.34),
        min_size=14.0,
        char_width_factor=0.48,
        uppercase=True,
    )
    masthead_name_size = fit_text_to_box(
        text=model.newspaper_name_text or "ILTA-SANOMAT",
        box_width=content_w * 0.98,
        box_height=masthead_zone_h * 0.58,
        start_size=min(56.0, masthead_zone_h * 0.50),
        min_size=30.0,
        char_width_factor=0.46,
        uppercase=False,
    )
    masthead_label_size, masthead_name_size = _fit_masthead_stack(
        label_size=masthead_label_size,
        name_size=masthead_name_size,
        zone_height=masthead_zone_h,
    )
    masthead_similarity_warning = masthead_name_size < 38.0 or masthead_label_size < 16.0

    headline_zone_h = (layout_params.headline_zone[1] - layout_params.headline_zone[0]) * page_height_pt
    main_headline_size = fit_text_to_box(
        text=model.main_headline,
        box_width=content_w,
        box_height=headline_zone_h * 0.55,
        start_size=min(42.0, headline_zone_h * 0.42),
        min_size=18.0,
        char_width_factor=0.52,
        uppercase=True,
    )
    secondary_headline_size = fit_text_to_box(
        text=model.secondary_headline,
        box_width=content_w,
        box_height=headline_zone_h * 0.40,
        start_size=min(34.0, headline_zone_h * 0.34),
        min_size=14.0,
        char_width_factor=0.52,
        uppercase=True,
    )
    lower_zone_h = (
        layout_params.bottom_headline_zone[1] - layout_params.bottom_headline_zone[0]
    ) * page_height_pt
    lower_headline_size = fit_text_to_box(
        text=model.bottom_headline,
        box_width=content_w,
        box_height=lower_zone_h * 0.7,
        start_size=min(28.0, lower_zone_h * 0.55),
        min_size=14.0,
        char_width_factor=0.55,
        uppercase=False,
    )

    warnings: list[str] = []
    overflow_warnings: list[str] = []

    masthead_mode: MastheadRenderMode = (
        "text" if render_masthead_as_text or not allow_text_crops else "crop"
    )

    meta_bbox = _meta_bbox_source(model)
    meta_row = MetaRowModel(
        issue_number=model.issue_number,
        date_text=model.date_text,
        stars=model.stars_text or "***",
        price=model.price_text,
        bbox_source=meta_bbox,
        confidence=_meta_confidence(model),
    )

    caption_model: ImageCaptionModel | None = None
    if model.image_caption.strip():
        caption_model = ImageCaptionModel(
            text=model.image_caption,
            bbox=None,
            related_image_id="hero_image",
        )
    elif model.main_story.caption is not None:
        caption_model = ImageCaptionModel(
            text=model.main_story.caption.text,
            bbox=_bbox_tuple(model.main_story.caption.bbox),
            related_image_id="hero_image",
        )

    if caption_model is None and model.main_story.caption is None:
        pass

    styles: dict[FontRole, TypographyStyle] = {
        FontRole.MASTHEAD_LABEL: _style(
            FontRole.MASTHEAD_LABEL,
            "Arial Black",
            "Impact",
            size=masthead_label_size,
            weight="bold",
            condensed=True,
            uppercase=True,
            color=BODY_GRAY,
            align="C",
            fpdf_family="ArBlk",
            fpdf_style="",
            min_size=14.0,
            max_size=28.0,
        ),
        FontRole.NEWSPAPER_NAME: _style(
            FontRole.NEWSPAPER_NAME,
            "Georgia Bold Italic",
            "Times New Roman Bold Italic",
            size=masthead_name_size,
            weight="bold",
            condensed=False,
            uppercase=False,
            color=ACCENT,
            align="C",
            fpdf_family="Ge",
            fpdf_style="BI",
            min_size=30.0,
            max_size=58.0,
        ),
        FontRole.ISSUE_META: _style(
            FontRole.ISSUE_META,
            "Times New Roman",
            "Georgia",
            size=meta_size,
            weight="normal",
            condensed=False,
            uppercase=False,
            color=BODY_GRAY,
            align="L",
            fpdf_family="Tm",
            fpdf_style="",
        ),
        FontRole.MAIN_HEADLINE: _style(
            FontRole.MAIN_HEADLINE,
            "Arial Black",
            "Impact",
            size=main_headline_size,
            weight="bold",
            condensed=True,
            uppercase=True,
            color=BODY_GRAY,
            align="C",
            fpdf_family="ArBlk",
            fpdf_style="",
            min_size=18.0,
            max_size=48.0,
        ),
        FontRole.SECONDARY_HEADLINE: _style(
            FontRole.SECONDARY_HEADLINE,
            "Arial Black",
            "Impact",
            size=secondary_headline_size,
            weight="bold",
            condensed=True,
            uppercase=True,
            color=BODY_GRAY,
            align="C",
            fpdf_family="ArBlk",
            fpdf_style="",
            min_size=14.0,
            max_size=38.0,
        ),
        FontRole.HERO_SIDEBAR_BODY: _style(
            FontRole.HERO_SIDEBAR_BODY,
            "Times New Roman",
            "Georgia",
            size=body_size,
            weight="normal",
            condensed=False,
            uppercase=False,
            color=BODY_GRAY,
            align="L",
            fpdf_family="Tm",
            fpdf_style="",
            min_size=body_min_font_size,
            max_size=9.0,
        ),
        FontRole.IMAGE_CAPTION: _style(
            FontRole.IMAGE_CAPTION,
            "Times New Roman",
            "Georgia",
            size=caption_size,
            weight="normal",
            condensed=False,
            uppercase=False,
            color=BODY_GRAY,
            align="L",
            fpdf_family="Tm",
            fpdf_style="I",
            min_size=5.0,
            max_size=8.0,
        ),
        FontRole.LOWER_HEADLINE: _style(
            FontRole.LOWER_HEADLINE,
            "Arial Black",
            "Impact",
            size=lower_headline_size,
            weight="bold",
            condensed=True,
            uppercase=False,
            color=BODY_GRAY,
            align="C",
            fpdf_family="ArBlk",
            fpdf_style="",
            min_size=14.0,
            max_size=32.0,
        ),
        FontRole.BOTTOM_COLUMN_BODY: _style(
            FontRole.BOTTOM_COLUMN_BODY,
            "Times New Roman",
            "Georgia",
            size=bottom_size,
            weight="normal",
            condensed=False,
            uppercase=False,
            color=BODY_GRAY,
            align="L",
            fpdf_family="Tm",
            fpdf_style="",
            min_size=bottom_column_min_font_size,
            max_size=8.5,
        ),
        FontRole.CONTINUATION_BOX: _style(
            FontRole.CONTINUATION_BOX,
            "Arial",
            "Arial",
            size=8.5,
            weight="bold",
            condensed=False,
            uppercase=True,
            color=(255, 255, 255),
            align="C",
            fpdf_family="Ar",
            fpdf_style="B",
        ),
    }

    if main_headline_size < body_size * 3:
        warnings.append("main_headline_font_size_below_3x_body")
    if lower_headline_size < body_size * 2:
        warnings.append("lower_headline_font_size_below_2x_body")
    if masthead_similarity_warning:
        warnings.append("masthead_similarity_below_target")

    return TypographyPlan(
        styles=styles,
        meta_row=meta_row,
        caption=caption_model,
        masthead_render_mode=masthead_mode,
        headline_font_size=main_headline_size,
        secondary_headline_font_size=secondary_headline_size,
        body_font_size=body_size,
        caption_font_size=caption_size,
        bottom_column_font_size=bottom_size,
        lower_headline_font_size=lower_headline_size,
        masthead_similarity_warning=masthead_similarity_warning,
        warnings=warnings,
        overflow_warnings=overflow_warnings,
    )


def fit_text_to_box(
    *,
    text: str,
    box_width: float,
    box_height: float,
    start_size: float,
    min_size: float,
    char_width_factor: float = 0.52,
    uppercase: bool = False,
) -> float:
    """Shrink font size until single-line text fits box width and height."""
    display = text.upper() if uppercase else text
    if not display.strip():
        return start_size
    size = start_size
    while size >= min_size:
        max_chars = max(1, int(box_width / (size * char_width_factor)))
        if len(display) <= max_chars and size * 1.15 <= box_height:
            return size
        size -= 0.5
    return min_size


def save_style_debug(*, plan: TypographyPlan, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(plan.to_debug_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def _fit_masthead_stack(
    *,
    label_size: float,
    name_size: float,
    zone_height: float,
    min_label: float = 14.0,
    min_name: float = 30.0,
) -> tuple[float, float]:
    """Ensure masthead label + newspaper name fit vertically in the masthead zone."""
    max_stack = zone_height * 0.90
    ls = label_size
    ns = name_size
    while ls * 1.15 + ns * 1.12 > max_stack and ns > min_name:
        ns -= 0.5
    while ls * 1.15 + ns * 1.12 > max_stack and ls > min_label:
        ls -= 0.5
    return ls, ns


def _style(
    role: FontRole,
    candidate: str,
    fallback: str,
    *,
    size: float,
    weight: Literal["normal", "bold"],
    condensed: bool,
    uppercase: bool,
    color: tuple[int, int, int],
    align: Literal["L", "C", "R"],
    fpdf_family: str,
    fpdf_style: str,
    min_size: float = 6.0,
    max_size: float = 48.0,
) -> TypographyStyle:
    return TypographyStyle(
        role=role,
        font_family_candidate=candidate,
        fallback_font=fallback,
        font_size=size,
        font_weight=weight,
        is_condensed=condensed,
        is_uppercase=uppercase,
        color=color,
        alignment=align,
        line_spacing=1.12,
        letter_spacing=0.0,
        max_width=None,
        min_font_size=min_size,
        max_font_size=max_size,
        fpdf_family=fpdf_family,
        fpdf_style=fpdf_style,
    )


def _meta_bbox_source(model: NewspaperFrontPageModel) -> tuple[float, float, float, float] | None:
    boxes = [
        block.bbox
        for block in (
            model.meta.issue_number,
            model.meta.date_text,
            model.meta.stars,
            model.meta.price,
        )
        if block is not None and block.bbox is not None
    ]
    if not boxes:
        return None
    x1 = min(box.x1 for box in boxes)
    y1 = min(box.y1 for box in boxes)
    x2 = max(box.x2 for box in boxes)
    y2 = max(box.y2 for box in boxes)
    return (x1, y1, x2, y2)


def _meta_confidence(model: NewspaperFrontPageModel) -> float:
    scores = [
        block.confidence
        for block in (
            model.meta.issue_number,
            model.meta.date_text,
            model.meta.stars,
            model.meta.price,
        )
        if block is not None
    ]
    return sum(scores) / len(scores) if scores else 0.85


def _bbox_tuple(bbox: object | None) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    return (bbox.x1, bbox.y1, bbox.x2, bbox.y2)  # type: ignore[union-attr]
