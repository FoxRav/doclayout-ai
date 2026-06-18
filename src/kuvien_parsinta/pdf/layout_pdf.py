"""Layout-preserving PDF renderers: rebuild, clean, debug overlay."""

from __future__ import annotations

from pathlib import Path

import cv2
from fpdf import FPDF

from kuvien_parsinta.layout.page_layout import (
    BlockRenderMode,
    FontRole,
    LayoutBlock,
    PageLayout,
)
from kuvien_parsinta.pdf.layout_helpers import font_size_for_role, wrap_text
from kuvien_parsinta.pdf.render import BODY_GRAY, WIN_FONT_BOLD, WIN_FONT_REG, render_markdown_to_pdf

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}


class LayoutPreservingPDF(FPDF):
    def __init__(self, *, width_pt: float, height_pt: float) -> None:
        super().__init__(unit="pt", format=(width_pt, height_pt))
        self.set_auto_page_break(False)
        self.set_margins(0, 0, 0)

    def register_fonts(self) -> None:
        for path in (WIN_FONT_REG, WIN_FONT_BOLD):
            if not path.is_file():
                raise FileNotFoundError(f"Font not found: {path}")
        self.add_font("Ar", "", str(WIN_FONT_REG))
        self.add_font("Ar", "B", str(WIN_FONT_BOLD))


def render_rebuild_pdf(
    *,
    source_path: Path,
    layout: PageLayout,
    pdf_path: Path,
    tmp_dir: Path | None = None,
) -> Path:
    """Rebuild page from absolute-positioned blocks — no markdown reflow."""
    if source_path.suffix.lower() not in _IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image for rebuild PDF: {source_path.suffix}")

    source = cv2.imread(str(source_path))
    if source is None:
        raise FileNotFoundError(f"Cannot read source image: {source_path}")

    pdf = LayoutPreservingPDF(width_pt=layout.pdf_width_pt, height_pt=layout.pdf_height_pt)
    pdf.register_fonts()
    pdf.add_page()
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(0, 0, layout.pdf_width_pt, layout.pdf_height_pt, style="F")

    for block in sorted(layout.blocks, key=lambda item: item.reading_order):
        if block.render_mode is BlockRenderMode.IMAGE:
            _draw_image_crop(pdf, source, block, tmp_dir=tmp_dir)
        elif block.render_mode is BlockRenderMode.BOX:
            _draw_box(pdf, block)
        elif block.text.strip():
            _draw_visible_text_in_bbox(pdf, block)

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(pdf_path))
    return pdf_path


def render_ocr_overlay_debug_pdf(
    *,
    source_path: Path,
    layout: PageLayout,
    pdf_path: Path,
    draw_bbox: bool = True,
) -> Path:
    """Debug PDF with visible bboxes and OCR text — never used as facsimile output."""
    if source_path.suffix.lower() not in _IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image for debug overlay PDF: {source_path.suffix}")

    pdf = LayoutPreservingPDF(width_pt=layout.pdf_width_pt, height_pt=layout.pdf_height_pt)
    pdf.register_fonts()
    pdf.add_page()
    pdf.image(str(source_path), x=0, y=0, w=layout.pdf_width_pt, h=layout.pdf_height_pt)

    for block in sorted(layout.blocks, key=lambda item: item.reading_order):
        if draw_bbox:
            _draw_debug_bbox(pdf, block)
        if block.text.strip() and block.render_mode is not BlockRenderMode.IMAGE:
            _draw_visible_text_in_bbox(pdf, block, label=block.block_type.value)

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(pdf_path))
    return pdf_path


def render_search_layer_debug_pdf(
    *,
    search_text: str,
    layout: PageLayout,
    pdf_path: Path,
) -> Path:
    """Debug PDF showing normalized search text — ocr/ only, never default output."""
    pdf = LayoutPreservingPDF(width_pt=layout.pdf_width_pt, height_pt=layout.pdf_height_pt)
    pdf.register_fonts()
    pdf.add_page()
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(0, 0, layout.pdf_width_pt, layout.pdf_height_pt, style="F")
    pdf.set_font("Ar", "", 9)
    pdf.set_text_color(*BODY_GRAY)
    pdf.set_xy(12, 12)
    pdf.multi_cell(layout.pdf_width_pt - 24, 11, search_text)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(pdf_path))
    return pdf_path


def render_clean_pdf(*, md_path: Path, pdf_path: Path) -> Path:
    """Readable reflowed PDF from markdown (not layout-preserving)."""
    return render_markdown_to_pdf(md_path=md_path, pdf_path=pdf_path)


def _draw_visible_text_in_bbox(
    pdf: LayoutPreservingPDF,
    block: LayoutBlock,
    *,
    label: str | None = None,
) -> None:
    bbox = block.bbox_pdf
    width = max(1.0, bbox.width)
    height = max(1.0, bbox.height)
    font_size = font_size_for_role(block.font_role, height)
    pdf.set_font("Ar", "B" if block.font_role is FontRole.HEADLINE else "", font_size)
    pdf.set_text_color(*BODY_GRAY)

    x = bbox.x1
    y = bbox.y1
    pdf.set_xy(x, y)
    line_height = font_size * 1.15
    prefix = f"[{label}] " if label else ""
    for line in wrap_text(f"{prefix}{block.text}", max_chars=max(8, int(width / (font_size * 0.55)))):
        if pdf.get_y() + line_height > bbox.y2:
            break
        pdf.set_x(x)
        pdf.cell(width, line_height, line, ln=True)


def _draw_debug_bbox(pdf: LayoutPreservingPDF, block: LayoutBlock) -> None:
    pdf.set_draw_color(255, 0, 0)
    pdf.set_line_width(0.6)
    pdf.rect(block.bbox_pdf.x1, block.bbox_pdf.y1, block.bbox_pdf.width, block.bbox_pdf.height)


def _draw_image_crop(
    pdf: LayoutPreservingPDF,
    source: object,
    block: LayoutBlock,
    *,
    tmp_dir: Path | None,
) -> None:
    bbox = block.bbox_px
    x1, y1, x2, y2 = int(bbox.x1), int(bbox.y1), int(bbox.x2), int(bbox.y2)
    crop = source[y1:y2, x1:x2]
    if crop.size == 0:
        return
    base = tmp_dir if tmp_dir is not None else Path(".tmp_layout_crops")
    base.mkdir(parents=True, exist_ok=True)
    tmp = base / f"{block.id}.jpg"
    cv2.imwrite(str(tmp), crop)
    pdf.image(str(tmp), x=block.bbox_pdf.x1, y=block.bbox_pdf.y1, w=block.bbox_pdf.width)


def _draw_box(pdf: LayoutPreservingPDF, block: LayoutBlock) -> None:
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.8)
    pdf.rect(block.bbox_pdf.x1, block.bbox_pdf.y1, block.bbox_pdf.width, block.bbox_pdf.height)
