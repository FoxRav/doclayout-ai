"""Deterministic newspaper front-page PDF with typography layer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2

from kuvien_parsinta.config import Settings
from kuvien_parsinta.layout.newspaper_page_model import NewspaperPageModel
from kuvien_parsinta.layout.page_layout import PageLayout
from kuvien_parsinta.layout.source_anchors import (
    CompactSpacing,
    RenderBox,
    SourceAnchoredLayout,
    build_source_anchors,
    resolve_source_anchored_layout,
)
from kuvien_parsinta.layout.typography_model import (
    FontRole,
    TypographyPlan,
    TypographyStyle,
    build_typography_plan,
    fit_text_to_box,
    save_style_debug,
)
from kuvien_parsinta.quality.source_alignment_metrics import (
    build_source_alignment_metrics,
    save_source_alignment_metrics,
)
from kuvien_parsinta.quality.visual_layout_metrics import (
    build_visual_layout_metrics,
    save_visual_metrics,
)
from kuvien_parsinta.text.final_text_cleanup import cleanup_final_text
from kuvien_parsinta.pdf.layout_helpers import wrap_text
from kuvien_parsinta.pdf.layout_pdf import LayoutPreservingPDF
from kuvien_parsinta.pdf.newspaper_fonts import font_is_registered, register_newspaper_fonts
from kuvien_parsinta.pdf.structural_newspaper_pdf import (
    StructuralRenderReport,
    pdf_contains_full_page_background,
)


@dataclass(frozen=True, slots=True)
class HeroPlacement:
    x: float
    y: float
    width: float
    height: float

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @classmethod
    def from_box(cls, box: RenderBox) -> HeroPlacement:
        return cls(x=box.x, y=box.y, width=box.width, height=box.height)


@dataclass(frozen=True, slots=True)
class TemplateZone:
    y_start: float
    y_end: float
    x_start: float = 0.0
    x_end: float = 1.0

    def rect_pt(self, page_w: float, page_h: float) -> tuple[float, float, float, float]:
        return (
            page_w * self.x_start,
            page_h * self.y_start,
            page_w * self.x_end,
            page_h * self.y_end,
        )


def render_newspaper_template_pdf(
    *,
    model: NewspaperPageModel,
    layout: PageLayout,
    pdf_path: Path,
    source_path: Path | None = None,
    settings: Settings | None = None,
    tmp_dir: Path | None = None,
    style_debug_path: Path | None = None,
    visual_metrics_path: Path | None = None,
    source_alignment_path: Path | None = None,
) -> tuple[Path, StructuralRenderReport, TypographyPlan]:
    """Render source-anchored structural newspaper PDF with compact spacing."""
    from kuvien_parsinta.config import get_settings

    cfg = settings or get_settings()
    page_w = layout.pdf_width_pt
    page_h = layout.pdf_height_pt
    spacing = CompactSpacing(
        newspaper_compact=cfg.newspaper_compact,
        vertical_gap_scale=cfg.vertical_gap_scale,
        headline_to_image_gap_ratio=cfg.headline_to_image_gap_ratio,
        image_to_caption_gap_ratio=cfg.image_to_caption_gap_ratio,
        caption_to_lower_headline_gap_ratio=cfg.caption_to_lower_headline_gap_ratio,
        lower_headline_to_columns_gap_ratio=cfg.lower_headline_to_columns_gap_ratio,
        margin_ratio=cfg.structural_margin_ratio,
    )
    anchors = build_source_anchors(layout=layout, model=model)
    anchored = resolve_source_anchored_layout(
        anchors=anchors,
        page_w_pt=page_w,
        page_h_pt=page_h,
        spacing=spacing,
    )

    plan = build_typography_plan(
        model=model,
        page_width_pt=page_w,
        page_height_pt=page_h,
        layout_params=_layout_params_from_anchored(anchored, page_h, page_w),
        body_min_font_size=cfg.body_min_font_size,
        bottom_column_min_font_size=cfg.bottom_column_min_font_size,
        render_masthead_as_text=cfg.render_masthead_as_text,
        allow_text_crops=cfg.allow_text_crops,
        allow_overflow_report=cfg.allow_text_overflow_report,
    )

    pdf = LayoutPreservingPDF(width_pt=page_w, height_pt=page_h)
    register_newspaper_fonts(pdf)
    pdf.add_page()
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(0, 0, page_w, page_h, style="F")

    placed: dict[str, RenderBox] = {}
    masthead_overlap = _draw_masthead(
        pdf,
        model,
        plan,
        anchored.masthead,
    )
    placed["masthead"] = anchored.masthead

    _draw_meta_row(pdf, plan, anchored.meta_row)
    placed["meta_row"] = anchored.meta_row

    headline_bottom = _draw_headlines(
        pdf, model, plan, anchored.headline_group, page_w
    )
    placed["headline_group"] = RenderBox(
        x=anchored.headline_group.x,
        y=anchored.headline_group.y,
        width=anchored.headline_group.width,
        height=max(anchored.headline_group.height, headline_bottom - anchored.headline_group.y),
    )

    hero = _draw_hero_image(pdf, model, anchored.hero_image)
    placed["hero_image"] = RenderBox(
        x=hero.x,
        y=hero.y,
        width=hero.width,
        height=hero.height,
    )

    sidebar_rendered = _draw_sidebar(
        pdf,
        model,
        plan,
        anchored.right_sidebar,
        hero=hero,
    )
    placed["right_sidebar"] = RenderBox(
        x=anchored.right_sidebar.x,
        y=hero.y,
        width=anchored.right_sidebar.width,
        height=hero.height,
    )

    caption_rendered = _draw_caption(pdf, model, plan, anchored.caption, hero=hero)
    placed["caption"] = anchored.caption

    lower_bottom = _draw_bottom_headline(pdf, model, plan, anchored.lower_headline)
    placed["lower_headline"] = RenderBox(
        x=anchored.lower_headline.x,
        y=anchored.lower_headline.y,
        width=anchored.lower_headline.width,
        height=max(anchored.lower_headline.height, lower_bottom - anchored.lower_headline.y),
    )

    bottom_columns_count, overflow = _draw_bottom_columns(
        pdf, model, plan, anchored.bottom_columns, cfg
    )
    placed["bottom_columns"] = anchored.bottom_columns
    if overflow and cfg.allow_text_overflow_report:
        plan.overflow_warnings.extend(overflow)

    _draw_continuation_box(pdf, model, plan, anchored.continuation)
    placed["continuation"] = anchored.continuation

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(pdf_path))

    if style_debug_path is not None:
        save_style_debug(plan=plan, output_path=style_debug_path)

    photo_crops_used = model.hero_image_crop_path is not None and model.hero_image_crop_path.is_file()
    visual_metrics = build_visual_layout_metrics(
        layout_boxes=anchored,
        page_h_pt=page_h,
        page_w_pt=page_w,
        masthead_render_mode=plan.masthead_render_mode,
        masthead_overlap=masthead_overlap,
        bottom_column_font_size=plan.bottom_column_font_size,
        placed=placed,
        text_crops_used=False,
        photo_crops_used=photo_crops_used,
        forbidden_text_crop_blocks=[],
        newspaper_name_render_mode="text",
        headlines_render_mode="text",
        metadata_render_mode="text",
        caption_render_mode="text",
        continuation_text_render_mode="text",
    )
    if visual_metrics_path is not None:
        save_visual_metrics(metrics=visual_metrics, output_path=visual_metrics_path)

    if source_alignment_path is not None:
        alignment = build_source_alignment_metrics(
            anchors=anchors,
            layout=anchored,
            page_h_pt=page_h,
            page_w_pt=page_w,
            placed=placed,
        )
        save_source_alignment_metrics(metrics=alignment, output_path=source_alignment_path)

    uses_full_page_bg = pdf_contains_full_page_background(
        pdf_path,
        page_width_pt=page_w,
        page_height_pt=page_h,
    )
    report = StructuralRenderReport(
        pdf_mode="structural_source_anchored",
        uses_full_page_background=uses_full_page_bg,
        uses_cropped_images_only=not uses_full_page_bg,
        main_headline_rendered_as_text=bool(model.main_headline.strip()),
        secondary_headline_rendered_as_text=bool(model.secondary_headline.strip()),
        bottom_headline_rendered_as_text=bool(model.bottom_headline.strip()),
        hero_image_is_crop=model.hero_image_crop_path is not None,
        right_sidebar_found=bool(model.right_sidebar_text.strip()),
        right_sidebar_rendered=sidebar_rendered,
        image_caption_rendered=caption_rendered,
        bottom_columns_count=bottom_columns_count,
        markdown_reflow_used=False,
        facsimile_used_as_primary=False,
    )
    return pdf_path, report, plan


def _layout_params_from_anchored(
    anchored: SourceAnchoredLayout,
    page_h: float,
    page_w: float,
) -> object:
    from kuvien_parsinta.layout.typography_model import StructuralLayoutParams

    def rel(box: RenderBox) -> tuple[float, float]:
        return (box.y / page_h, (box.y + box.height) / page_h)

    margin_ratio = anchored.margin / page_w if page_w > 0 else 0.035
    return StructuralLayoutParams(
        margin_ratio=margin_ratio,
        compact_vertical=True,
        page_scale="large",
        hero_width_ratio=anchored.hero_width_ratio,
        sidebar_width_ratio=anchored.sidebar_width_ratio,
        masthead_zone=rel(anchored.masthead),
        meta_zone=rel(anchored.meta_row),
        headline_zone=rel(anchored.headline_group),
        middle_zone=rel(anchored.hero_image),
        caption_zone=rel(anchored.caption),
        bottom_headline_zone=rel(anchored.lower_headline),
        bottom_columns_zone=rel(anchored.bottom_columns),
    )


def save_template_render_report(*, report: StructuralRenderReport, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_json_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def _zone_from_params(
    y_range: tuple[float, float],
    *,
    margin_ratio: float,
    x_end: float = 1.0,
) -> TemplateZone:
    return TemplateZone(
        y_start=y_range[0],
        y_end=y_range[1],
        x_start=margin_ratio,
        x_end=x_end,
    )


def _apply_style(pdf: LayoutPreservingPDF, style: TypographyStyle) -> None:
    family_chain = [style.fpdf_family]
    if style.fpdf_family == "ArBlk":
        family_chain.append("Ar")
    elif style.fpdf_family == "Ge":
        family_chain.extend(["Tm", "Ar"])
    elif style.fpdf_family == "Tm":
        family_chain.append("Ar")

    style_chain = [style.fpdf_style]
    if style.fpdf_style == "BI":
        style_chain.extend(["B", "I", ""])
    elif style.fpdf_style:
        style_chain.append("")

    family = style.fpdf_family
    fpdf_style = style.fpdf_style
    for candidate_family in family_chain:
        for candidate_style in style_chain:
            if font_is_registered(pdf, candidate_family, candidate_style):
                family = candidate_family
                fpdf_style = candidate_style
                break
        else:
            continue
        break
    else:
        family = "Ar"
        fpdf_style = "B" if style.font_weight == "bold" else ""

    pdf.set_font(family, fpdf_style, style.font_size)
    pdf.set_text_color(*style.color)


def _draw_masthead(
    pdf: LayoutPreservingPDF,
    model: NewspaperPageModel,
    plan: TypographyPlan,
    box: RenderBox,
) -> bool:
    """Draw masthead as PDF text; return True if text-mode overlap detected."""
    overlap = False
    label_style = plan.styles[FontRole.MASTHEAD_LABEL]
    name_style = plan.styles[FontRole.NEWSPAPER_NAME]
    label_text = model.masthead_text.upper() if label_style.is_uppercase else model.masthead_text
    stack_height = (
        label_style.font_size * label_style.line_spacing
        + 1.0
        + name_style.font_size * name_style.line_spacing
    )
    label_y = box.y + max(1.0, (box.height - stack_height) / 2)
    name_y = label_y + label_style.font_size * label_style.line_spacing + 1.0

    _apply_style(pdf, label_style)
    pdf.set_xy(box.x, label_y)
    pdf.cell(box.width, label_style.font_size * label_style.line_spacing, label_text, align="C")

    _apply_style(pdf, name_style)
    pdf.set_xy(box.x, name_y)
    pdf.cell(
        box.width,
        name_style.font_size * name_style.line_spacing,
        model.newspaper_name_text,
        align="C",
    )

    stack_bottom = name_y + name_style.font_size * name_style.line_spacing
    if stack_bottom > box.bottom + 0.5:
        overlap = True
        plan.warnings.append("masthead_overlap_detected")
    elif name_y - label_y < label_style.font_size * 1.0:
        overlap = True
        plan.warnings.append("masthead_overlap_detected")
    return overlap


def _draw_meta_row(
    pdf: LayoutPreservingPDF,
    plan: TypographyPlan,
    box: RenderBox,
) -> None:
    style = plan.styles[FontRole.ISSUE_META]
    _apply_style(pdf, style)
    row_y = box.y + (box.height - style.font_size) / 2
    left_w = box.width * 0.28
    center_w = box.width * 0.36
    stars_w = box.width * 0.12
    right_w = box.width * 0.24

    pdf.set_xy(box.x, row_y)
    pdf.cell(left_w, style.font_size * style.line_spacing, plan.meta_row.issue_number, align="L")
    pdf.set_xy(box.x + left_w, row_y)
    pdf.cell(center_w, style.font_size * style.line_spacing, plan.meta_row.date_text, align="C")
    pdf.set_xy(box.x + left_w + center_w, row_y)
    pdf.cell(stars_w, style.font_size * style.line_spacing, plan.meta_row.stars, align="C")
    pdf.set_xy(box.x + box.width - right_w, row_y)
    pdf.cell(right_w, style.font_size * style.line_spacing, plan.meta_row.price, align="R")

    line_y = box.y + box.height - 1.0
    pdf.set_draw_color(*style.color)
    pdf.set_line_width(0.5)
    pdf.line(box.x, line_y, box.x + box.width, line_y)


def _draw_headlines(
    pdf: LayoutPreservingPDF,
    model: NewspaperPageModel,
    plan: TypographyPlan,
    box: RenderBox,
    page_w: float,
) -> float:
    y_cursor = box.y + 1.0
    x1 = box.x
    width = box.width

    if model.main_headline.strip():
        main_style = plan.styles[FontRole.MAIN_HEADLINE]
        lines = model.main_headline.splitlines() if "\n" in model.main_headline else [model.main_headline]
        for line in lines[:2]:
            text = line.upper() if main_style.is_uppercase else line
            _apply_style(pdf, main_style)
            pdf.set_xy(x1, y_cursor)
            pdf.cell(width, main_style.font_size * main_style.line_spacing, text.strip(), align="C")
            y_cursor += main_style.font_size * main_style.line_spacing + 1.0

    if model.secondary_headline.strip():
        sub_style = plan.styles[FontRole.SECONDARY_HEADLINE]
        text = model.secondary_headline.upper() if sub_style.is_uppercase else model.secondary_headline
        _apply_style(pdf, sub_style)
        pdf.set_xy(x1, y_cursor)
        pdf.cell(width, sub_style.font_size * sub_style.line_spacing, text, align="C")
        y_cursor += sub_style.font_size * sub_style.line_spacing + 1.0

    pdf.set_draw_color(*plan.styles[FontRole.MAIN_HEADLINE].color)
    pdf.set_line_width(0.8)
    pdf.line(x1 + width * 0.08, y_cursor + 1.0, x1 + width * 0.92, y_cursor + 1.0)
    return y_cursor + 2.0


def _draw_hero_image(
    pdf: LayoutPreservingPDF,
    model: NewspaperPageModel,
    box: RenderBox,
) -> HeroPlacement:
    if model.hero_image_crop_path is None or not model.hero_image_crop_path.is_file():
        return HeroPlacement.from_box(box)

    hero_h = box.height
    source = cv2.imread(str(model.hero_image_crop_path))
    if source is not None:
        img_h, img_w = source.shape[:2]
        if img_w > 0:
            hero_h = min(box.height, box.width * (img_h / img_w))

    pdf.image(
        str(model.hero_image_crop_path),
        x=box.x,
        y=box.y,
        w=box.width,
        h=hero_h,
        keep_aspect_ratio=True,
    )
    return HeroPlacement(x=box.x, y=box.y, width=box.width, height=hero_h)


def _draw_sidebar(
    pdf: LayoutPreservingPDF,
    model: NewspaperPageModel,
    plan: TypographyPlan,
    box: RenderBox,
    *,
    hero: HeroPlacement,
) -> bool:
    sidebar_text = cleanup_final_text(model.right_sidebar_text.strip())
    if not sidebar_text:
        return False

    from dataclasses import replace

    base_style = plan.styles[FontRole.HERO_SIDEBAR_BODY]
    max_height = max(1.0, hero.height)
    min_size = 5.5
    font_size = max(min_size, base_style.font_size)
    lines_drawn = 0
    overflow = True

    while font_size >= min_size:
        style = replace(base_style, font_size=font_size)
        line_height = style.font_size * style.line_spacing
        max_chars = max(8, int(box.width / (style.font_size * 0.48)))
        lines = list(wrap_text(sidebar_text, max_chars=max_chars))
        needed_height = len(lines) * line_height
        if needed_height <= max_height:
            overflow = False
            break
        font_size -= 0.25

    style = replace(base_style, font_size=font_size)
    lines_drawn, clipped = _draw_wrapped_text(
        pdf,
        text=sidebar_text,
        x=box.x,
        y=hero.y,
        width=box.width,
        max_height=max_height,
        style=style,
    )
    if overflow or clipped:
        plan.overflow_warnings.append("sidebar_text_overflow")
    return lines_drawn > 0


def _draw_caption(
    pdf: LayoutPreservingPDF,
    model: NewspaperPageModel,
    plan: TypographyPlan,
    box: RenderBox,
    *,
    hero: HeroPlacement,
) -> bool:
    caption_text = cleanup_final_text(
        plan.caption.text if plan.caption is not None else model.image_caption.strip()
    )
    if not caption_text:
        return False

    style = plan.styles[FontRole.IMAGE_CAPTION]
    x1 = hero.x
    y1 = hero.bottom + 2.0
    width = hero.width
    line_height = style.font_size * style.line_spacing
    max_chars = max(8, int(width / (style.font_size * 0.46)))

    _apply_style(pdf, style)
    lines_drawn = 0
    current_y = y1
    for line in wrap_text(caption_text, max_chars=max_chars):
        if lines_drawn >= 2:
            break
        if current_y + line_height > y1 + box.height:
            break
        pdf.set_xy(x1, current_y)
        pdf.cell(width, line_height, line, align=style.alignment)
        current_y += line_height
        lines_drawn += 1
    return lines_drawn > 0


def _draw_bottom_headline(
    pdf: LayoutPreservingPDF,
    model: NewspaperPageModel,
    plan: TypographyPlan,
    box: RenderBox,
) -> float:
    if not model.bottom_headline.strip():
        return box.y

    style = plan.styles[FontRole.LOWER_HEADLINE]
    _apply_style(pdf, style)
    y = box.y + (box.height - style.font_size) / 2
    pdf.set_xy(box.x, y)
    pdf.cell(
        box.width,
        style.font_size * style.line_spacing,
        cleanup_final_text(model.bottom_headline),
        align="C",
    )
    return y + style.font_size * style.line_spacing


def _draw_bottom_columns(
    pdf: LayoutPreservingPDF,
    model: NewspaperPageModel,
    plan: TypographyPlan,
    box: RenderBox,
    cfg: Settings,
) -> tuple[int, list[str]]:
    columns = [cleanup_final_text(text) for text in model.bottom_column_texts if text.strip()]
    if not columns:
        return 0, []

    col_count = len(columns)
    gap = 4.0
    col_width = (box.width - gap * (col_count - 1)) / col_count
    style = plan.styles[FontRole.BOTTOM_COLUMN_BODY]
    overflow: list[str] = []

    for idx, col_text in enumerate(columns):
        col_x = box.x + idx * (col_width + gap)
        _lines, clipped = _draw_wrapped_text(
            pdf,
            text=col_text,
            x=col_x,
            y=box.y,
            width=col_width,
            max_height=box.height,
            style=style,
        )
        if clipped and cfg.allow_text_overflow_report:
            overflow.append(f"bottom_column_{idx}_overflow")

    return col_count, overflow


def _draw_continuation_box(
    pdf: LayoutPreservingPDF,
    model: NewspaperPageModel,
    plan: TypographyPlan,
    box: RenderBox,
) -> None:
    if not model.continuation_text.strip():
        return

    pdf.set_fill_color(0, 0, 0)
    pdf.rect(box.x, box.y, box.width, box.height, style="F")

    style = plan.styles[FontRole.CONTINUATION_BOX]
    _apply_style(pdf, style)
    pdf.set_xy(box.x + 4, box.y + (box.height - style.font_size) / 2)
    pdf.cell(box.width - 8, style.font_size, model.continuation_text, align="C")


def _draw_wrapped_text(
    pdf: LayoutPreservingPDF,
    *,
    text: str,
    x: float,
    y: float,
    width: float,
    max_height: float,
    style: TypographyStyle,
) -> tuple[int, bool]:
    """Draw wrapped text; return (lines_drawn, clipped)."""
    _apply_style(pdf, style)
    line_height = style.font_size * style.line_spacing
    max_chars = max(8, int(width / (style.font_size * 0.48)))
    y_limit = y + max_height
    clipped = False
    lines_drawn = 0
    current_y = y
    for line in wrap_text(text, max_chars=max_chars):
        if current_y + line_height > y_limit:
            clipped = True
            break
        pdf.set_xy(x, current_y)
        pdf.cell(width, line_height, line, align=style.alignment)
        current_y += line_height
        lines_drawn += 1
    pdf.set_xy(x, current_y)
    return lines_drawn, clipped

