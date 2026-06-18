"""Structural PDF must rebuild layout — not embed full-page source image."""

from __future__ import annotations

from pathlib import Path

from kuvien_parsinta.layout.newspaper_page_model import build_newspaper_page_model
from kuvien_parsinta.layout.page_layout_builder import build_page_layout
from kuvien_parsinta.pdf.newspaper_template_renderer import render_newspaper_template_pdf
from kuvien_parsinta.pdf.structural_newspaper_pdf import (
    count_embedded_images,
    extract_visible_pdf_text,
    pdf_contains_full_page_background,
)


def test_structural_pdf_not_facsimile(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    image = repo / "parsittavat" / "Paukku" / "paukku.jpg"
    structure = repo / "parsittavat" / "Paukku" / "ocr" / "paukku_structurev3_res.json"
    if not structure.is_file():
        structure = repo / "parsittavat" / "Paukku" / "ocr" / "paukku_res.json"
    vl = repo / "parsittavat" / "Paukku" / "ocr" / "paukku_vl_res.json"
    if not image.is_file() or not structure.is_file():
        return

    layout = build_page_layout(
        source_path=image,
        structure_json_path=structure,
        vl_json_path=vl if vl.is_file() else None,
    )
    assert layout is not None

    model = build_newspaper_page_model(
        layout=layout,
        source_path=image,
        vl_json_path=vl if vl.is_file() else None,
        tmp_dir=tmp_path / "crops",
    )
    pdf_path = tmp_path / "paukku_structural.pdf"
    _, report, _ = render_newspaper_template_pdf(model=model, layout=layout, pdf_path=pdf_path)

    assert report.uses_full_page_background is False
    assert report.facsimile_used_as_primary is False
    assert report.markdown_reflow_used is False
    assert report.hero_image_is_crop is True
    assert report.main_headline_rendered_as_text is True

    assert pdf_contains_full_page_background(
        pdf_path,
        page_width_pt=layout.pdf_width_pt,
        page_height_pt=layout.pdf_height_pt,
    ) is False

    assert count_embedded_images(pdf_path) >= 1

    visible = extract_visible_pdf_text(pdf_path).upper()
    assert "KUOLONUHRIA" in visible
    assert "TEHDASR" in visible and "YKSESS" in visible
    assert "ILTA-SANOMAT" in visible
