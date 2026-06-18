"""Regression: newspaper typography roles and font hierarchy."""

from __future__ import annotations

import json
from pathlib import Path

import fitz

from kuvien_parsinta.config import Settings
from kuvien_parsinta.layout.newspaper_page_model import build_newspaper_page_model
from kuvien_parsinta.layout.page_layout_builder import build_page_layout
from kuvien_parsinta.layout.typography_model import build_typography_plan, resolve_layout_params
from kuvien_parsinta.pdf.newspaper_template_renderer import render_newspaper_template_pdf
from kuvien_parsinta.quality.newspaper_quality_gate import run_newspaper_quality_gate


def test_newspaper_typography_roles(tmp_path: Path) -> None:
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
    settings = Settings()
    layout_params = resolve_layout_params(
        margin_ratio=settings.structural_margin_ratio,
        compact_vertical=settings.structural_compact_vertical,
        page_scale=settings.structural_page_scale,
    )
    plan = build_typography_plan(
        model=model,
        page_width_pt=layout.pdf_width_pt,
        page_height_pt=layout.pdf_height_pt,
        layout_params=layout_params,
        body_min_font_size=settings.body_min_font_size,
        bottom_column_min_font_size=settings.bottom_column_min_font_size,
        render_masthead_as_text=settings.render_masthead_as_text,
        allow_text_crops=settings.allow_text_crops,
        allow_overflow_report=settings.allow_text_overflow_report,
    )

    assert plan.headline_font_size > plan.body_font_size * 3
    assert plan.lower_headline_font_size > plan.body_font_size * 2
    assert plan.bottom_column_font_size >= settings.bottom_column_min_font_size
    assert "1 MK" in model.price_text.upper()
    assert not model.right_sidebar_text.upper().startswith("1 MK")

    style_debug = tmp_path / "style_debug.json"
    pdf_path = tmp_path / "paukku_structural.pdf"
    _, _, _ = render_newspaper_template_pdf(
        model=model,
        layout=layout,
        pdf_path=pdf_path,
        source_path=image,
        settings=settings,
        tmp_dir=tmp_path / "crops",
        style_debug_path=style_debug,
    )

    payload = json.loads(style_debug.read_text(encoding="utf-8"))
    assert payload["masthead_render_mode"] == "text"
    assert payload["headline_font_size"] > payload["body_font_size"] * 3

    doc = fitz.open(str(pdf_path))
    try:
        text = doc[0].get_text().upper()
        assert "KUOLONUHRIA" in text
        assert "JATKUU" in text
    finally:
        doc.close()

    md_path = tmp_path / "paukku.md"
    md_path.write_text("# test\n", encoding="utf-8-sig")
    gate = run_newspaper_quality_gate(
        stem="paukku",
        target_dir=tmp_path,
        ocr_dir=tmp_path / "ocr",
        markdown_path=md_path,
        structural_pdf_path=pdf_path,
        pdf_width_pt=layout.pdf_width_pt,
        pdf_height_pt=layout.pdf_height_pt,
        emit_facsimile=False,
        page_model=model,
        style_debug_path=style_debug,
    )
    typography_checks = {
        c.name: c.passed
        for c in gate.checks
        if "font_size" in c.name or "masthead" in c.name or "style_debug" in c.name
    }
    assert typography_checks.get("style_debug_exists") is True
    assert typography_checks.get("main_headline_font_size_gt_3x_body") is True
    assert typography_checks.get("lower_headline_font_size_gt_2x_body") is True
