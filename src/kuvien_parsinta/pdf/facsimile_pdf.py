"""Facsimile PDF: full-page source image + invisible searchable OCR text (PyMuPDF)."""

from __future__ import annotations

from pathlib import Path

import cv2
import fitz
import numpy as np

from kuvien_parsinta.layout.page_layout import PageLayout
from kuvien_parsinta.pdf.layout_helpers import wrap_text
from kuvien_parsinta.pdf.render import WIN_FONT_REG

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
_INVISIBLE_FONT = "invisible-ar"


def render_facsimile_pdf(
    *,
    source_path: Path,
    layout: PageLayout,
    pdf_path: Path,
    search_text: str | None = None,
    invisible_text: bool = True,
    visible_ocr: bool = False,
    metadata: dict[str, str] | None = None,
) -> Path:
    """Render archive-grade facsimile: visible source image only, OCR as invisible text layer."""
    if visible_ocr:
        raise ValueError("Facsimile PDF must not render visible OCR text (visible_ocr=false)")
    if source_path.suffix.lower() not in _IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image for facsimile PDF: {source_path.suffix}")

    doc = fitz.open()
    page = doc.new_page(width=layout.pdf_width_pt, height=layout.pdf_height_pt)
    page_rect = fitz.Rect(0, 0, layout.pdf_width_pt, layout.pdf_height_pt)
    page.insert_image(page_rect, filename=str(source_path))

    if invisible_text and search_text and search_text.strip():
        fontname = _register_invisible_font(page)
        _insert_invisible_search_stream(
            page,
            search_text,
            fontname=fontname,
            page_height_pt=layout.pdf_height_pt,
        )

    doc.set_metadata(_facsimile_metadata(metadata))
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def extract_pdf_text(pdf_path: Path) -> str:
    doc = fitz.open(str(pdf_path))
    try:
        return doc[0].get_text()
    finally:
        doc.close()


def pdf_page_to_bgr(pdf_path: Path, *, dpi: int = 150) -> np.ndarray:
    doc = fitz.open(str(pdf_path))
    try:
        page = doc[0]
        scale = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        channels = pix.n
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, channels)
        if channels == 4:
            return cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    finally:
        doc.close()


def raster_similarity_to_source(
    source_path: Path,
    pdf_path: Path,
    *,
    dpi: int = 150,
) -> float:
    """Return 1.0 when rasterized PDF matches source; lower when visible overlay differs."""
    source = cv2.imread(str(source_path))
    if source is None:
        raise FileNotFoundError(f"Cannot read source image: {source_path}")
    rendered = pdf_page_to_bgr(pdf_path, dpi=dpi)
    height, width = rendered.shape[:2]
    resized = cv2.resize(source, (width, height), interpolation=cv2.INTER_AREA)
    diff = cv2.absdiff(resized, rendered)
    mean_abs = float(np.mean(diff))
    return 1.0 - (mean_abs / 255.0)


def _register_invisible_font(page: fitz.Page) -> str:
    if WIN_FONT_REG.is_file():
        page.insert_font(fontname=_INVISIBLE_FONT, fontfile=str(WIN_FONT_REG))
        return _INVISIBLE_FONT
    return "helv"


def _insert_invisible_search_stream(
    page: fitz.Page,
    search_text: str,
    *,
    fontname: str,
    page_height_pt: float,
) -> None:
    """Embed one logical reading-order text stream (invisible, does not affect raster)."""
    font_size = 10.0
    line_height = font_size * 1.25
    x = 1.0
    y = line_height
    max_y = page_height_pt - line_height

    for paragraph in search_text.split("\n\n"):
        paragraph_lines: list[str] = []
        for line in paragraph.split("\n"):
            stripped = line.strip()
            if stripped:
                paragraph_lines.append(stripped)
        if not paragraph_lines:
            continue
        for wrapped in paragraph_lines:
            for piece in wrap_text(wrapped, max_chars=120):
                if y > max_y:
                    return
                page.insert_text(
                    fitz.Point(x, y),
                    piece,
                    fontsize=font_size,
                    fontname=fontname,
                    render_mode=3,
                    overlay=True,
                )
                y += line_height
        y += line_height * 0.5


def _facsimile_metadata(extra: dict[str, str] | None) -> dict[str, str]:
    custom = {
        "engine": "hybrid",
        "text_source": "paddleocr_vl",
        "layout_source": "pp_structurev3",
        "pdf_mode": "facsimile",
        "visible_ocr": "false",
    }
    if extra:
        custom.update(extra)
    keywords = "; ".join(f"{key}={value}" for key, value in custom.items())
    return {
        "producer": "kuvien-parsinta",
        "creator": "kuvien-parsinta hybrid",
        "subject": "facsimile layout-preserving archive PDF",
        "keywords": keywords,
    }
