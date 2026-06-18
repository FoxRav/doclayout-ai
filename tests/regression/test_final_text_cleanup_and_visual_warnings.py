"""Regression: final text cleanup and visual finishing quality warnings."""

from __future__ import annotations

import json
from pathlib import Path

import fitz

from kuvien_parsinta.config import Settings
from kuvien_parsinta.layout.page_layout_builder import build_page_layout
from kuvien_parsinta.markdown.newspaper_markdown import build_newspaper_markdown
from kuvien_parsinta.pdf.newspaper_template_renderer import render_newspaper_template_pdf
from kuvien_parsinta.quality.newspaper_quality_gate import is_soft_quality_check, run_newspaper_quality_gate
from kuvien_parsinta.text.final_text_cleanup import cleanup_final_text, text_cleanup_issues
from tests.regression.paukku_helpers import build_assembled_paukku_model


def test_final_text_cleanup_literals() -> None:
    raw = "pelätään. vielä lisääntyvän.\n1 mk (sis. lvv\non-\nnettomuusalueelle"
    cleaned = cleanup_final_text(raw)
    assert "pelätään. vielä" not in cleaned.lower()
    assert "pelätään vielä" in cleaned.lower()
    assert "1 mk (sis. lvv)" in cleaned.lower()
    assert "onnettomuusalueelle" in cleaned.lower()
    assert not text_cleanup_issues(cleaned)


def test_final_text_cleanup_and_visual_warnings_paukku(tmp_path: Path) -> None:
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
    ocr_dir = tmp_path / "ocr"
    pdf_path = tmp_path / "paukku_structural.pdf"
    style_debug = ocr_dir / "paukku_style_debug.json"
    visual_metrics = ocr_dir / "paukku_visual_metrics.json"
    alignment_metrics = ocr_dir / "paukku_source_alignment_metrics.json"
    render_newspaper_template_pdf(
        model=model,
        layout=layout,
        pdf_path=pdf_path,
        source_path=image,
        settings=settings,
        tmp_dir=tmp_path / "crops",
        style_debug_path=style_debug,
        visual_metrics_path=visual_metrics,
        source_alignment_path=alignment_metrics,
    )

    markdown = build_newspaper_markdown(
        layout=layout,
        vl_json_path=vl if vl.is_file() else None,
        fallback_markdown="fallback",
        model=model,
    )
    md_path = tmp_path / "paukku.md"
    md_path.write_text(markdown, encoding="utf-8-sig")

    assert "pelätään. vielä" not in markdown.lower()
    assert "\ufffd" not in markdown
    assert "1 mk (sis. lvv)" in markdown.lower()

    doc = fitz.open(str(pdf_path))
    try:
        pdf_text = doc[0].get_text()
    finally:
        doc.close()

    assert "on\ufffdnettomuus" not in pdf_text.lower()
    assert "on- nettomuus" not in pdf_text.lower()

    metrics = json.loads(visual_metrics.read_text(encoding="utf-8"))
    assert metrics["bottom_column_font_size"] >= 5.5
    assert "total_vertical_whitespace_ratio" in metrics
    assert "headline_to_hero_gap_ratio" in metrics
    assert "hero_to_caption_gap_ratio" in metrics

    style_payload = json.loads(style_debug.read_text(encoding="utf-8"))
    assert "masthead_similarity_warning" in style_payload

    assert alignment_metrics.is_file()

    gate = run_newspaper_quality_gate(
        stem="paukku",
        target_dir=tmp_path,
        ocr_dir=ocr_dir,
        markdown_path=md_path,
        structural_pdf_path=pdf_path,
        pdf_width_pt=layout.pdf_width_pt,
        pdf_height_pt=layout.pdf_height_pt,
        emit_facsimile=False,
        page_model=model,
        style_debug_path=style_debug,
        visual_metrics_path=visual_metrics,
        content_audit_path=ocr_dir / "paukku_content_audit.json",
    )

    assert gate.passed is True
    assert gate.content_metrics is not None
    assert gate.content_metrics.get("content_quality") == "PASS"
    assert gate.content_metrics.get("bottom_columns_readability") in {"PASS", "WARN"}

    quality_result = str(gate.content_metrics.get("quality_result", ""))
    soft_failed = [c.name for c in gate.checks if not c.passed and is_soft_quality_check(c.name)]

    if soft_failed:
        assert quality_result == "PASS_WITH_WARNINGS"
        assert quality_result != "PASS"
    else:
        assert quality_result == "PASS"

    hard_failed = [c.name for c in gate.checks if not c.passed and not is_soft_quality_check(c.name)]
    assert not hard_failed, hard_failed

    assert gate.content_metrics.get("text_cleanup_pass") is True
