"""Tests for layout-preserving PDF coordinates and page layout."""

from __future__ import annotations

from pathlib import Path

import pytest

from kuvien_parsinta.layout.page_layout import BboxPx
from kuvien_parsinta.pdf.coordinates import bbox_px_to_pdf, page_pdf_dimensions


def test_page_pdf_preserves_aspect_ratio() -> None:
    w, h, sx, sy = page_pdf_dimensions(source_width_px=1000, source_height_px=1500)
    assert abs(w / h - 1000 / 1500) < 0.001
    assert sx == pytest.approx(w / 1000)
    assert sy == pytest.approx(h / 1500)


def test_bbox_px_to_pdf_flips_y_axis() -> None:
    _, pdf_h, sx, sy = page_pdf_dimensions(source_width_px=100, source_height_px=200)
    bbox = BboxPx(10, 20, 90, 180)
    pdf_bbox = bbox_px_to_pdf(bbox, pdf_height_pt=pdf_h, scale_x=sx, scale_y=sy)
    assert pdf_bbox.x1 == pytest.approx(10 * sx)
    assert pdf_bbox.x2 == pytest.approx(90 * sx)
    assert pdf_bbox.y2 == pytest.approx(pdf_h - 20 * sy)
    assert pdf_bbox.y1 == pytest.approx(pdf_h - 180 * sy)


def test_build_page_layout_from_paukku_if_present() -> None:
    repo = Path(__file__).resolve().parents[2]
    image = repo / "parsittavat" / "Paukku" / "paukku.jpg"
    structure = repo / "parsittavat" / "Paukku" / "ocr" / "paukku_structurev3_res.json"
    if not structure.is_file():
        structure = repo / "parsittavat" / "Paukku" / "ocr" / "paukku_res.json"
    vl = repo / "parsittavat" / "Paukku" / "ocr" / "paukku_vl_res.json"
    if not image.is_file() or not structure.is_file():
        return

    from kuvien_parsinta.layout.page_layout import DocumentType, NewspaperBlockType
    from kuvien_parsinta.layout.page_layout_builder import build_page_layout

    layout = build_page_layout(
        source_path=image,
        structure_json_path=structure,
        vl_json_path=vl if vl.is_file() else None,
    )
    assert layout is not None
    assert layout.page_width_px > 0
    assert len(layout.blocks) > 0
    types = {block.block_type for block in layout.blocks}
    assert NewspaperBlockType.HERO_IMAGE in types or NewspaperBlockType.MAIN_HEADLINE in types
    if layout.document_type is DocumentType.NEWSPAPER_FRONT_PAGE:
        assert layout.pdf_width_pt / layout.pdf_height_pt == pytest.approx(
            layout.page_width_px / layout.page_height_px,
            rel=0.01,
        )
