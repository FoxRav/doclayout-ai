"""Regression: source-anchored visual layout metrics for newspaper PDF."""

from __future__ import annotations

import json
from pathlib import Path

import fitz

from kuvien_parsinta.config import Settings
from kuvien_parsinta.layout.page_layout_builder import build_page_layout
from kuvien_parsinta.markdown.newspaper_markdown import build_newspaper_markdown
from kuvien_parsinta.pdf.newspaper_template_renderer import render_newspaper_template_pdf
from kuvien_parsinta.quality.newspaper_quality_gate import is_soft_quality_check, run_newspaper_quality_gate
from tests.regression.paukku_helpers import build_assembled_paukku_model


def test_newspaper_visual_layout_metrics(tmp_path: Path) -> None:
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

    model = build_assembled_paukku_model(
        layout=layout,
        image=image,
        structure=structure,
        vl=vl if vl.is_file() else None,
        tmp_dir=tmp_path / "crops",
    )

    settings = Settings()
    assert settings.render_masthead_as_text is True
    assert settings.allow_text_crops is False

    pdf_path = tmp_path / "paukku_structural.pdf"
    style_debug = tmp_path / "ocr" / "paukku_style_debug.json"
    visual_metrics = tmp_path / "ocr" / "paukku_visual_metrics.json"
    _, report, _ = render_newspaper_template_pdf(
        model=model,
        layout=layout,
        pdf_path=pdf_path,
        source_path=image,
        settings=settings,
        tmp_dir=tmp_path / "crops",
        style_debug_path=style_debug,
        visual_metrics_path=visual_metrics,
    )

    payload = json.loads(visual_metrics.read_text(encoding="utf-8"))
    assert payload["masthead_overlap"] is False
    assert payload["hero_image_width_ratio"] >= 0.70
    assert payload["right_sidebar_width_ratio"] >= 0.18
    assert payload["bottom_column_font_size"] >= 5.5
    assert payload["image_to_caption_gap_ratio"] <= 0.028
    assert payload["masthead_render_mode"] == "text"

    doc = fitz.open(str(pdf_path))
    try:
        text = doc[0].get_text()
        page_h = layout.pdf_height_pt
        blocks = doc[0].get_text("dict")["blocks"]
        hero_y = None
        headline_y = None
        for block in blocks:
            if block.get("type") != 0:
                continue
            block_text = "".join(
                span.get("text", "")
                for line in block.get("lines", [])
                for span in line.get("spans", [])
            )
            if "KUOLONUHRIA" in block_text.upper() and headline_y is None:
                headline_y = block["bbox"][1] / page_h
            if headline_y is not None and hero_y is None and block.get("type") == 1:
                hero_y = block["bbox"][1] / page_h
        if hero_y is not None and headline_y is not None:
            assert headline_y < hero_y
    finally:
        doc.close()

    assert report.right_sidebar_rendered is True

    root_pdfs = list(tmp_path.glob("*.pdf"))
    assert len(root_pdfs) == 1
    assert root_pdfs[0].name == "paukku_structural.pdf"

    markdown = build_newspaper_markdown(
        layout=layout,
        vl_json_path=vl if vl.is_file() else None,
        fallback_markdown="fallback",
        model=model,
    )
    md_path = tmp_path / "paukku.md"
    md_path.write_text(markdown, encoding="utf-8-sig")
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
        visual_metrics_path=visual_metrics,
        content_audit_path=tmp_path / "ocr" / "paukku_content_audit.json",
    )
    assert gate.passed is True
    hard_failed = [c.name for c in gate.checks if not c.passed and not is_soft_quality_check(c.name)]
    assert not hard_failed, hard_failed
