"""Facsimile PDF must not show visible OCR overlay on the source image."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from kuvien_parsinta.layout.page_layout import (
    BlockRenderMode,
    BboxPx,
    BboxPt,
    DocumentType,
    FontRole,
    LayoutBlock,
    NewspaperBlockType,
    PageLayout,
)
from kuvien_parsinta.pdf.coordinates import bbox_px_to_pdf, page_pdf_dimensions
from kuvien_parsinta.pdf.facsimile_pdf import (
    extract_pdf_text,
    raster_similarity_to_source,
    render_facsimile_pdf,
)
from kuvien_parsinta.pdf.search_text_layer import build_search_text_layer


def _sample_layout(*, page_w: int, page_h: int, ocr_text: str) -> PageLayout:
    pdf_w, pdf_h, scale_x, scale_y = page_pdf_dimensions(
        source_width_px=page_w,
        source_height_px=page_h,
    )
    bbox_px = BboxPx(40, 80, page_w - 40, 180)
    bbox_pdf = bbox_px_to_pdf(bbox_px, pdf_height_pt=pdf_h, scale_x=scale_x, scale_y=scale_y)
    block = LayoutBlock(
        id="t0",
        block_type=NewspaperBlockType.BODY_TEXT,
        bbox_px=bbox_px,
        bbox_pdf=bbox_pdf,
        text=ocr_text,
        source_engine="test",
        confidence=0.9,
        reading_order=0,
        font_role=FontRole.BODY,
        render_mode=BlockRenderMode.TEXT,
    )
    return PageLayout(
        page_width_px=page_w,
        page_height_px=page_h,
        pdf_width_pt=pdf_w,
        pdf_height_pt=pdf_h,
        scale_x=scale_x,
        scale_y=scale_y,
        document_type=DocumentType.GENERIC,
        blocks=(block,),
    )


def _write_test_image(path: Path, *, width: int = 400, height: int = 300) -> None:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.rectangle(image, (0, 0), (width - 1, height - 1), (30, 90, 180), thickness=-1)
    cv2.putText(
        image,
        "SOURCE",
        (120, 160),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (240, 240, 240),
        2,
        cv2.LINE_AA,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(path), image)


def test_facsimile_has_no_visible_ocr_overlay(tmp_path: Path) -> None:
    source = tmp_path / "sample.jpg"
    pdf_path = tmp_path / "sample_facsimile.pdf"
    ocr_text = "Hakukelpoinen teksti facsimile PDF:ssä"
    _write_test_image(source)
    layout = _sample_layout(page_w=400, page_h=300, ocr_text=ocr_text)
    search_layer = build_search_text_layer(layout=layout, vl_json_path=None)

    render_facsimile_pdf(
        source_path=source,
        layout=layout,
        pdf_path=pdf_path,
        search_text=search_layer.full_text,
        invisible_text=True,
        visible_ocr=False,
    )

    similarity = raster_similarity_to_source(source, pdf_path, dpi=150)
    assert similarity > 0.98, f"Visible OCR overlay detected (similarity={similarity:.4f})"

    extracted = extract_pdf_text(pdf_path)
    assert "Hakukelpoinen" in extracted
    assert "teksti" in extracted


def test_facsimile_rejects_visible_ocr_flag(tmp_path: Path) -> None:
    source = tmp_path / "sample.jpg"
    pdf_path = tmp_path / "sample_facsimile.pdf"
    _write_test_image(source)
    layout = _sample_layout(page_w=400, page_h=300, ocr_text="piilotettu")

    with pytest.raises(ValueError, match="visible OCR"):
        render_facsimile_pdf(
            source_path=source,
            layout=layout,
            pdf_path=pdf_path,
            visible_ocr=True,
        )


def test_paukku_facsimile_if_present(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    image = repo / "parsittavat" / "Paukku" / "paukku.jpg"
    structure = repo / "parsittavat" / "Paukku" / "ocr" / "paukku_structurev3_res.json"
    if not structure.is_file():
        structure = repo / "parsittavat" / "Paukku" / "ocr" / "paukku_res.json"
    vl = repo / "parsittavat" / "Paukku" / "ocr" / "paukku_vl_res.json"
    if not image.is_file() or not structure.is_file():
        return

    from kuvien_parsinta.layout.page_layout_builder import build_page_layout

    layout = build_page_layout(
        source_path=image,
        structure_json_path=structure,
        vl_json_path=vl if vl.is_file() else None,
    )
    assert layout is not None
    search_layer = build_search_text_layer(
        layout=layout,
        vl_json_path=vl if vl.is_file() else None,
    )

    out = tmp_path / "paukku_facsimile.pdf"
    render_facsimile_pdf(
        source_path=image,
        layout=layout,
        pdf_path=out,
        search_text=search_layer.full_text,
        invisible_text=True,
        visible_ocr=False,
    )
    similarity = raster_similarity_to_source(image, out, dpi=100)
    assert similarity > 0.98, f"Paukku facsimile shows visible overlay (similarity={similarity:.4f})"
    extracted = extract_pdf_text(out)
    assert len(extracted.strip()) > 200, "Facsimile PDF should contain searchable OCR text"
