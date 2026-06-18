"""Structural newspaper PDF: fixed-layout rebuild without full-page background."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import fitz

from kuvien_parsinta.layout.page_layout import (
    BlockRenderMode,
    FontRole,
    LayoutBlock,
    NewspaperBlockType,
    PageLayout,
)
from kuvien_parsinta.pdf.layout_helpers import font_size_for_role, wrap_text
from kuvien_parsinta.pdf.layout_pdf import LayoutPreservingPDF, _draw_image_crop
from kuvien_parsinta.pdf.render import ACCENT, BODY_GRAY
from kuvien_parsinta.pdf.search_text_layer import deduplicated_layout_blocks

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
_FULL_PAGE_COVERAGE_THRESHOLD = 0.90


@dataclass(frozen=True, slots=True)
class StructuralRenderReport:
    pdf_mode: str
    uses_full_page_background: bool
    uses_cropped_images_only: bool
    main_headline_rendered_as_text: bool
    secondary_headline_rendered_as_text: bool
    bottom_headline_rendered_as_text: bool
    hero_image_is_crop: bool
    right_sidebar_found: bool
    bottom_columns_count: int
    markdown_reflow_used: bool
    facsimile_used_as_primary: bool
    right_sidebar_rendered: bool = False
    image_caption_rendered: bool = False

    def to_json_dict(self) -> dict[str, object]:
        return {
            "pdf_mode": self.pdf_mode,
            "uses_full_page_background": self.uses_full_page_background,
            "uses_cropped_images_only": self.uses_cropped_images_only,
            "main_headline_rendered_as_text": self.main_headline_rendered_as_text,
            "secondary_headline_rendered_as_text": self.secondary_headline_rendered_as_text,
            "bottom_headline_rendered_as_text": self.bottom_headline_rendered_as_text,
            "hero_image_is_crop": self.hero_image_is_crop,
            "right_sidebar_found": self.right_sidebar_found,
            "right_sidebar_rendered": self.right_sidebar_rendered,
            "image_caption_rendered": self.image_caption_rendered,
            "bottom_columns_count": self.bottom_columns_count,
            "markdown_reflow_used": self.markdown_reflow_used,
            "facsimile_used_as_primary": self.facsimile_used_as_primary,
        }


def render_structural_newspaper_pdf(
    *,
    source_path: Path,
    layout: PageLayout,
    pdf_path: Path,
    vl_json_path: Path | None = None,
    tmp_dir: Path | None = None,
) -> tuple[Path, StructuralRenderReport]:
    """Rebuild newspaper page from typed blocks and cropped images — no full-page background."""
    if source_path.suffix.lower() not in _IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image for structural PDF: {source_path.suffix}")

    source = cv2.imread(str(source_path))
    if source is None:
        raise FileNotFoundError(f"Cannot read source image: {source_path}")

    blocks = _prepare_structural_blocks(
        deduplicated_layout_blocks(layout=layout, vl_json_path=vl_json_path),
        layout=layout,
    )

    pdf = LayoutPreservingPDF(width_pt=layout.pdf_width_pt, height_pt=layout.pdf_height_pt)
    pdf.register_fonts()
    pdf.add_page()
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(0, 0, layout.pdf_width_pt, layout.pdf_height_pt, style="F")

    rendered_types: set[NewspaperBlockType] = set()
    hero_crop_drawn = False

    for block in blocks:
        if block.render_mode is BlockRenderMode.IMAGE:
            _draw_image_crop(pdf, source, block, tmp_dir=tmp_dir)
            if block.block_type is NewspaperBlockType.HERO_IMAGE:
                hero_crop_drawn = True
            continue
        if not block.text.strip():
            continue
        _draw_structural_block(pdf, block)
        rendered_types.add(block.block_type)

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(pdf_path))

    uses_full_page_bg = pdf_contains_full_page_background(
        pdf_path,
        page_width_pt=layout.pdf_width_pt,
        page_height_pt=layout.pdf_height_pt,
    )
    report = StructuralRenderReport(
        pdf_mode="structural",
        uses_full_page_background=uses_full_page_bg,
        uses_cropped_images_only=not uses_full_page_bg,
        main_headline_rendered_as_text=NewspaperBlockType.MAIN_HEADLINE in rendered_types,
        secondary_headline_rendered_as_text=NewspaperBlockType.SECONDARY_HEADLINE in rendered_types,
        bottom_headline_rendered_as_text=NewspaperBlockType.BOTTOM_HEADLINE in rendered_types,
        hero_image_is_crop=hero_crop_drawn,
        right_sidebar_found=NewspaperBlockType.RIGHT_SIDEBAR in rendered_types,
        bottom_columns_count=sum(
            1 for block in blocks if block.block_type is NewspaperBlockType.BOTTOM_COLUMNS
        ),
        markdown_reflow_used=False,
        facsimile_used_as_primary=False,
    )
    return pdf_path, report


def save_structural_report(*, report: StructuralRenderReport, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_json_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def pdf_contains_full_page_background(
    pdf_path: Path,
    *,
    page_width_pt: float,
    page_height_pt: float,
) -> bool:
    """True when a single embedded image covers most of the page (facsimile-style background)."""
    doc = fitz.open(str(pdf_path))
    try:
        page = doc[0]
        page_area = max(1.0, page_width_pt * page_height_pt)
        for image in page.get_images(full=True):
            xref = int(image[0])
            for rect in page.get_image_rects(xref):
                coverage = (rect.width * rect.height) / page_area
                if coverage >= _FULL_PAGE_COVERAGE_THRESHOLD:
                    return True
        return False
    finally:
        doc.close()


def extract_visible_pdf_text(pdf_path: Path) -> str:
    doc = fitz.open(str(pdf_path))
    try:
        return doc[0].get_text()
    finally:
        doc.close()


def count_embedded_images(pdf_path: Path) -> int:
    doc = fitz.open(str(pdf_path))
    try:
        return len(doc[0].get_images(full=True))
    finally:
        doc.close()


def _prepare_structural_blocks(
    blocks: tuple[LayoutBlock, ...],
    *,
    layout: PageLayout,
) -> tuple[LayoutBlock, ...]:
    image_blocks = [block for block in layout.blocks if block.render_mode is BlockRenderMode.IMAGE]
    text_blocks = _expand_split_headlines(list(blocks))
    combined = list(image_blocks) + text_blocks
    return tuple(sorted(combined, key=_structural_z_order))


def _structural_z_order(block: LayoutBlock) -> tuple[int, float, float]:
    if block.render_mode is BlockRenderMode.IMAGE:
        return (0, block.bbox_px.y1, block.bbox_px.x1)
    if block.block_type is NewspaperBlockType.CONTINUATION_BOX:
        return (3, block.bbox_px.y1, block.bbox_px.x1)
    return (1, block.bbox_px.y1, block.bbox_px.x1)


def _expand_split_headlines(blocks: list[LayoutBlock]) -> list[LayoutBlock]:
    expanded: list[LayoutBlock] = []
    for block in blocks:
        if block.block_type is not NewspaperBlockType.MAIN_HEADLINE:
            expanded.append(block)
            continue
        lines = [line.strip() for line in block.text.splitlines() if line.strip()]
        if len(lines) <= 1:
            expanded.append(block)
            continue
        expanded.append(_replace_block_text(block, lines[0], NewspaperBlockType.MAIN_HEADLINE))
        for idx, line in enumerate(lines[1:], start=1):
            expanded.append(
                _replace_block_text(
                    block,
                    line,
                    NewspaperBlockType.SECONDARY_HEADLINE,
                    block_id=f"{block.id}_sub{idx}",
                    y_offset_pt=idx * 14.0,
                )
            )
    return expanded


def _replace_block_text(
    block: LayoutBlock,
    text: str,
    block_type: NewspaperBlockType,
    *,
    block_id: str | None = None,
    y_offset_pt: float = 0.0,
) -> LayoutBlock:
    bbox_pdf = block.bbox_pdf
    if y_offset_pt > 0:
        from kuvien_parsinta.layout.page_layout import BboxPt

        bbox_pdf = BboxPt(
            bbox_pdf.x1,
            bbox_pdf.y1 + y_offset_pt,
            bbox_pdf.x2,
            bbox_pdf.y2,
        )
    return LayoutBlock(
        id=block_id or block.id,
        block_type=block_type,
        bbox_px=block.bbox_px,
        bbox_pdf=bbox_pdf,
        text=text,
        source_engine=block.source_engine,
        confidence=block.confidence,
        reading_order=block.reading_order,
        font_role=FontRole.HEADLINE,
        render_mode=block.render_mode,
    )


def _draw_structural_block(pdf: LayoutPreservingPDF, block: LayoutBlock) -> None:
    match block.block_type:
        case NewspaperBlockType.NEWSPAPER_NAME:
            _draw_text_block(pdf, block, bold=True, color=ACCENT, scale=0.65)
        case NewspaperBlockType.MAIN_HEADLINE | NewspaperBlockType.SECONDARY_HEADLINE:
            _draw_text_block(pdf, block, bold=True, color=BODY_GRAY, scale=0.70)
        case NewspaperBlockType.BOTTOM_HEADLINE:
            _draw_text_block(pdf, block, bold=True, color=BODY_GRAY, scale=0.62)
        case NewspaperBlockType.CONTINUATION_BOX:
            _draw_continuation_box(pdf, block)
        case NewspaperBlockType.IMAGE_CAPTION:
            _draw_text_block(pdf, block, bold=False, color=BODY_GRAY, scale=0.40)
        case NewspaperBlockType.RIGHT_SIDEBAR | NewspaperBlockType.BOTTOM_COLUMNS:
            _draw_text_block(pdf, block, bold=False, color=BODY_GRAY, scale=0.42)
        case NewspaperBlockType.ISSUE_META | NewspaperBlockType.MASTHEAD_LOGO:
            _draw_text_block(pdf, block, bold=False, color=BODY_GRAY, scale=0.45)
        case _:
            _draw_text_block(pdf, block, bold=False, color=BODY_GRAY, scale=0.45)


def _draw_text_block(
    pdf: LayoutPreservingPDF,
    block: LayoutBlock,
    *,
    bold: bool,
    color: tuple[int, int, int],
    scale: float,
) -> None:
    bbox = block.bbox_pdf
    width = max(1.0, bbox.width)
    height = max(1.0, bbox.height)
    font_size = min(font_size_for_role(block.font_role, height) * scale, height * 0.85)
    font_size = max(6.0, font_size)
    pdf.set_font("Ar", "B" if bold else "", font_size)
    pdf.set_text_color(*color)

    x = bbox.x1
    y = bbox.y1
    pdf.set_xy(x, y)
    line_height = font_size * 1.12
    max_chars = max(8, int(width / (font_size * 0.52)))
    for line in wrap_text(block.text, max_chars=max_chars):
        if pdf.get_y() + line_height > bbox.y2:
            break
        pdf.set_x(x)
        pdf.cell(width, line_height, line, ln=True)


def _draw_continuation_box(pdf: LayoutPreservingPDF, block: LayoutBlock) -> None:
    bbox = block.bbox_pdf
    pdf.set_fill_color(0, 0, 0)
    pdf.rect(bbox.x1, bbox.y1, bbox.width, bbox.height, style="F")
    font_size = max(7.0, min(11.0, bbox.height * 0.45))
    pdf.set_font("Ar", "B", font_size)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(bbox.x1 + 4, bbox.y1 + 4)
    pdf.multi_cell(bbox.width - 8, font_size * 1.1, block.text.strip())
