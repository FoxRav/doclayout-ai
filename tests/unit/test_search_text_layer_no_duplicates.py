"""Search text layer: deduplicated reading order for facsimile PDF search."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from kuvien_parsinta.pdf.search_text_layer import build_search_text_layer


def _count_phrase(text: str, phrase: str) -> int:
    normalized = re.sub(r"\s+", " ", text.upper())
    target = re.sub(r"\s+", " ", phrase.upper())
    return normalized.count(target)


def test_search_text_dedup_synthetic_duplicates() -> None:
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
    from kuvien_parsinta.pdf.coordinates import page_pdf_dimensions

    page_w, page_h = 800, 1200
    pdf_w, pdf_h, sx, sy = page_pdf_dimensions(source_width_px=page_w, source_height_px=page_h)

    def block(
        block_id: str,
        block_type: NewspaperBlockType,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        text: str,
    ) -> LayoutBlock:
        bbox_px = BboxPx(x1, y1, x2, y2)
        return LayoutBlock(
            id=block_id,
            block_type=block_type,
            bbox_px=bbox_px,
            bbox_pdf=BboxPt(x1 * sx, y1 * sy, x2 * sx, y2 * sy),
            text=text,
            source_engine="structurev3",
            confidence=0.8,
            reading_order=0,
            font_role=FontRole.BODY,
            render_mode=BlockRenderMode.TEXT,
        )

    duplicate_body = (
        "Jo 39 ihmistä oli löydetty kuolleena ja kymmeniä vakavasti loukkaantuneita "
        "kaivettu raunioista."
    )
    layout = PageLayout(
        page_width_px=page_w,
        page_height_px=page_h,
        pdf_width_pt=pdf_w,
        pdf_height_pt=pdf_h,
        scale_x=sx,
        scale_y=sy,
        document_type=DocumentType.NEWSPAPER_FRONT_PAGE,
        blocks=(
            block("a", NewspaperBlockType.MAIN_HEADLINE, 20, 100, 760, 200, "JO 39 KUOLONUHRIA"),
            block(
                "b",
                NewspaperBlockType.RIGHT_SIDEBAR,
                560,
                250,
                780,
                500,
                duplicate_body,
            ),
            block(
                "c",
                NewspaperBlockType.RIGHT_SIDEBAR,
                565,
                255,
                775,
                505,
                duplicate_body,
            ),
        ),
    )

    layer = build_search_text_layer(layout=layout, vl_json_path=None)
    assert _count_phrase(layer.full_text, "JO 39 KUOLONUHRIA") == 1
    assert _count_phrase(layer.full_text, "Jo 39 ihmistä") == 1
    assert len(layer.removed_duplicates) >= 1


def test_paukku_search_text_if_present(tmp_path: Path) -> None:
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

    layer = build_search_text_layer(
        layout=layout,
        vl_json_path=vl if vl.is_file() else None,
    )
    text = layer.full_text

    assert _count_phrase(text, "JO 39 KUOLONUHRIA") == 1
    assert "TEHDASR" in text.upper() and "JÄYKSESS" in text.upper()
    assert _count_phrase(text, "lentokielto") <= 1

    sidebar_marker = "Jo 39 ihmist"
    assert text.count(sidebar_marker) <= 1, "Right sidebar body must not duplicate"

    if "LAPUA ERIST" in text.upper():
        assert _count_phrase(text, "LAPUA ERIST") == 1

    assert layer.block_count_after < layer.block_count_before

    from kuvien_parsinta.pdf.facsimile_pdf import extract_pdf_text, render_facsimile_pdf

    pdf_out = tmp_path / "paukku_facsimile.pdf"
    render_facsimile_pdf(
        source_path=image,
        layout=layout,
        pdf_path=pdf_out,
        search_text=layer.full_text,
    )
    extracted = extract_pdf_text(pdf_out)
    assert _count_phrase(extracted, "JO 39 KUOLONUHRIA") == 1
