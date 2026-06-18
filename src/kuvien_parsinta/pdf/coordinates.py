"""Convert pixel bboxes to PDF point coordinates preserving aspect ratio."""

from __future__ import annotations

from kuvien_parsinta.layout.page_layout import BboxPx, BboxPt

DEFAULT_PDF_WIDTH_PT = 595.0


def page_pdf_dimensions(
    *,
    source_width_px: int,
    source_height_px: int,
    pdf_width_pt: float = DEFAULT_PDF_WIDTH_PT,
) -> tuple[float, float, float, float]:
    """Return pdf_width, pdf_height, scale_x, scale_y."""
    if source_width_px <= 0 or source_height_px <= 0:
        raise ValueError("Source image dimensions must be positive")
    pdf_height_pt = pdf_width_pt * source_height_px / source_width_px
    scale_x = pdf_width_pt / source_width_px
    scale_y = pdf_height_pt / source_height_px
    return pdf_width_pt, pdf_height_pt, scale_x, scale_y


def bbox_px_to_pdf(
    bbox: BboxPx,
    *,
    pdf_height_pt: float,
    scale_x: float,
    scale_y: float,
) -> BboxPt:
    """Map top-left image coords to PDF bottom-left origin."""
    x1_pt = bbox.x1 * scale_x
    x2_pt = bbox.x2 * scale_x
    y1_pt = pdf_height_pt - bbox.y2 * scale_y
    y2_pt = pdf_height_pt - bbox.y1 * scale_y
    return BboxPt(x1=x1_pt, y1=y1_pt, x2=x2_pt, y2=y2_pt)
