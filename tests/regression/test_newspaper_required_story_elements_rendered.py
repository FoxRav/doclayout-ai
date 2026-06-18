"""Regression: main story sidebar and image caption must appear in structural PDF."""

from __future__ import annotations

import json
from pathlib import Path

import fitz

from kuvien_parsinta.config import Settings
from kuvien_parsinta.layout.newspaper_page_model import build_newspaper_page_model
from kuvien_parsinta.layout.page_layout_builder import build_page_layout
from kuvien_parsinta.markdown.newspaper_markdown import build_newspaper_markdown
from kuvien_parsinta.pdf.newspaper_template_renderer import render_newspaper_template_pdf
from kuvien_parsinta.quality.newspaper_quality_gate import is_soft_quality_check, run_newspaper_quality_gate
from tests.regression.paukku_helpers import build_assembled_paukku_model


def test_newspaper_required_story_elements_rendered(tmp_path: Path) -> None:
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

    assert model.right_sidebar_text.strip().startswith("Jo 39 ihmistä")
    assert "Murhe" in model.image_caption
    assert model.story_content.image_caption_candidates_count >= 1
    assert "main_story.caption" not in model.main_story.missing_required_elements

    markdown = build_newspaper_markdown(
        layout=layout,
        vl_json_path=vl if vl.is_file() else None,
        fallback_markdown="fallback",
        model=model,
    )
    assert "*Kuvateksti:" in markdown
    assert "Murhe" in markdown

    settings = Settings()
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

    assert report.right_sidebar_rendered is True
    assert report.image_caption_rendered is True

    doc = fitz.open(str(pdf_path))
    try:
        pdf_text = doc[0].get_text()
    finally:
        doc.close()

    assert "Jo 39" in pdf_text
    assert "Murhe" in pdf_text

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

    payload = gate.to_json_dict()
    assert payload["content_loss_detected"] is False
    assert payload["main_story_sidebar_rendered"] is True
    assert payload["image_caption_rendered"] is True
    assert gate.status in {"pass", "pass_with_warnings"}
    assert gate.passed is True

    hard_failed = [check.name for check in gate.checks if not check.passed and not is_soft_quality_check(check.name)]
    assert not hard_failed, f"Quality gate hard failed: {hard_failed}"
