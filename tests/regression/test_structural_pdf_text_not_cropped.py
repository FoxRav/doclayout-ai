"""Regression: structural PDF must not embed text regions as raster crops."""

from __future__ import annotations

import json
from pathlib import Path

import fitz

from kuvien_parsinta.config import Settings
from kuvien_parsinta.layout.page_layout_builder import build_page_layout
from kuvien_parsinta.markdown.newspaper_markdown import build_newspaper_markdown
from kuvien_parsinta.pdf.newspaper_template_renderer import render_newspaper_template_pdf
from kuvien_parsinta.pdf.structural_newspaper_pdf import count_embedded_images
from kuvien_parsinta.quality.newspaper_quality_gate import is_soft_quality_check, run_newspaper_quality_gate
from tests.regression.paukku_helpers import build_assembled_paukku_model


def test_structural_pdf_text_not_cropped(tmp_path: Path) -> None:
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
    assert settings.allow_text_crops is False
    assert settings.render_masthead_as_text is True
    assert settings.allow_photo_crops is True

    pdf_path = tmp_path / "paukku_structural.pdf"
    style_debug = tmp_path / "ocr" / "paukku_style_debug.json"
    visual_metrics = tmp_path / "ocr" / "paukku_visual_metrics.json"
    _, report, plan = render_newspaper_template_pdf(
        model=model,
        layout=layout,
        pdf_path=pdf_path,
        source_path=image,
        settings=settings,
        tmp_dir=tmp_path / "crops",
        style_debug_path=style_debug,
        visual_metrics_path=visual_metrics,
    )

    assert plan.masthead_render_mode == "text"
    payload = json.loads(visual_metrics.read_text(encoding="utf-8"))
    assert payload["text_crops_used"] is False
    assert payload["photo_crops_used"] is True
    assert payload["masthead_render_mode"] == "text"
    assert payload["newspaper_name_render_mode"] == "text"
    assert payload["forbidden_text_crop_blocks"] == []

    image_count = count_embedded_images(pdf_path)
    assert image_count == 1

    doc = fitz.open(str(pdf_path))
    try:
        visible = doc[0].get_text().upper()
    finally:
        doc.close()

    for phrase in (
        "ILTA-SANOMAT",
        "JO 39 KUOLONUHRIA",
        "TEHDASR",
        "LAPUA ERISTET",
        "JATKUU",
    ):
        assert phrase in visible or phrase.replace("Ä", "A") in visible

    assert report.hero_image_is_crop is True
    assert report.main_headline_rendered_as_text is True

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
    assert gate.content_metrics is not None
    assert gate.content_metrics.get("text_crops_used") is False
    assert gate.content_metrics.get("photo_crops_used") is True

    hard_failed = [c.name for c in gate.checks if not c.passed and not is_soft_quality_check(c.name)]
    assert not hard_failed, hard_failed
