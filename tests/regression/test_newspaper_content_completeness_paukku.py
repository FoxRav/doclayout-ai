"""Regression: paukku newspaper content completeness and integrity."""

from __future__ import annotations

import json
import re
from pathlib import Path

import fitz

from kuvien_parsinta.config import Settings
from kuvien_parsinta.layout.page_layout_builder import build_page_layout
from kuvien_parsinta.markdown.newspaper_markdown import build_newspaper_markdown
from kuvien_parsinta.pdf.newspaper_template_renderer import render_newspaper_template_pdf
from kuvien_parsinta.quality.content_audit import run_content_audit, save_content_audit
from kuvien_parsinta.quality.newspaper_quality_gate import run_newspaper_quality_gate
from tests.regression.paukku_helpers import build_assembled_paukku_model


def test_newspaper_content_completeness_paukku(tmp_path: Path) -> None:
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
    pdf_path = tmp_path / "paukku_structural.pdf"
    style_debug = tmp_path / "ocr" / "paukku_style_debug.json"
    visual_metrics = tmp_path / "ocr" / "paukku_visual_metrics.json"
    render_newspaper_template_pdf(
        model=model,
        layout=layout,
        pdf_path=pdf_path,
        source_path=image,
        settings=settings,
        tmp_dir=tmp_path / "crops",
        style_debug_path=style_debug,
        visual_metrics_path=visual_metrics,
    )

    markdown = build_newspaper_markdown(
        layout=layout,
        vl_json_path=vl if vl.is_file() else None,
        fallback_markdown="fallback",
        model=model,
    )
    md_path = tmp_path / "paukku.md"
    md_path.write_text(markdown, encoding="utf-8-sig")

    doc = fitz.open(str(pdf_path))
    try:
        pdf_text = doc[0].get_text()
    finally:
        doc.close()

    md_lower = re.sub(r"\s+", " ", markdown.lower())
    pdf_lower = re.sub(r"\s+", " ", pdf_text.lower())
    sidebar = re.sub(r"\s+", " ", model.right_sidebar_text.lower())

    for phrase in (
        "jo 39 ihmistä oli löydetty",
        "onnettomuudessa loukkaantuneille",
        "murhe kasvoi",
        "vielä lisääntyvän",
        "räjähdys tapahtui tehtaan lataamorakennuksessa",
    ):
        norm_phrase = re.sub(r"\s+", " ", phrase)
        assert norm_phrase in md_lower, phrase
        assert norm_phrase in pdf_lower, phrase

    for forbidden in ("räjäh maata",):
        assert forbidden not in md_lower
        assert forbidden not in pdf_lower

    assert "lapua eristet" not in sidebar
    assert markdown.upper().count("LAPUA ERISTET") <= 1

    audit_path = tmp_path / "ocr" / "paukku_content_audit.json"
    audit = run_content_audit(
        page_model=model,
        markdown_path=md_path,
        structural_pdf_path=pdf_path,
        layout_quality="PASS",
    )
    save_content_audit(result=audit, output_path=audit_path)
    assert audit.content_quality == "PASS"

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
        content_audit_path=audit_path,
    )
    assert gate.passed is True
    assert gate.content_metrics is not None
    assert gate.content_metrics.get("content_quality") == "PASS"

    report = json.loads((tmp_path / "ocr" / "paukku_content_audit.json").read_text(encoding="utf-8"))
    assert report["content_quality"] == "PASS"
