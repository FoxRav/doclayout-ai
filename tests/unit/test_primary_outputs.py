"""Primary output files are always written on successful parse."""

from __future__ import annotations

from pathlib import Path

import pytest

from kuvien_parsinta.layout.newspaper_page_model import build_newspaper_page_model
from kuvien_parsinta.layout.page_layout_builder import build_page_layout
from kuvien_parsinta.markdown.newspaper_markdown import build_newspaper_markdown
from kuvien_parsinta.output.primary_outputs import has_utf8_bom, write_markdown, write_primary_outputs
from kuvien_parsinta.pdf.newspaper_template_renderer import render_newspaper_template_pdf
from kuvien_parsinta.pdf.output_policy import resolve_pdf_output_plan


def test_write_markdown_uses_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "sample.md"
    write_markdown(path=path, markdown_text="# Otsikko\n\nTekstiä.")
    assert path.is_file()
    assert has_utf8_bom(path)


def test_write_markdown_empty_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="primary markdown output was not written"):
        write_markdown(path=tmp_path / "unused.md", markdown_text="   ")


def test_paukku_newspaper_markdown_if_present() -> None:
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
        tmp_dir=None,
    )
    markdown = build_newspaper_markdown(
        layout=layout,
        vl_json_path=vl if vl.is_file() else None,
        fallback_markdown="fallback",
        model=model,
    )
    upper = markdown.upper()
    assert "KUOLONUHRIA" in upper
    assert "TEHDASR" in upper and "YKSESS" in upper
    assert markdown.count("# ") >= 1


def test_primary_outputs_in_tmp_only(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    image = repo / "parsittavat" / "Paukku" / "paukku.jpg"
    structure = repo / "parsittavat" / "Paukku" / "ocr" / "paukku_structurev3_res.json"
    if not structure.is_file():
        structure = repo / "parsittavat" / "Paukku" / "ocr" / "paukku_res.json"
    vl = repo / "parsittavat" / "Paukku" / "ocr" / "paukku_vl_res.json"
    if not image.is_file() or not structure.is_file():
        return

    from kuvien_parsinta.config import Settings
    from kuvien_parsinta.models import InputKind, ParseResult

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
    markdown = build_newspaper_markdown(
        layout=layout,
        vl_json_path=vl if vl.is_file() else None,
        fallback_markdown="# fallback",
        model=model,
    )

    settings = Settings(
        write_pdf=True,
        emit_facsimile=False,
        emit_clean=False,
        emit_debug_pdf=False,
    )
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    ocr_dir = settings.debug_dir(out_dir)

    result = ParseResult(
        source=image,
        markdown_path=out_dir / "paukku.md",
        engine_used="hybrid",
        primary_engine="hybrid",
    )

    def _render_pdfs(**kwargs: object) -> dict[str, Path | None]:
        source = kwargs["source"]
        assert isinstance(source, Path)
        target_dir = kwargs["target_dir"]
        assert isinstance(target_dir, Path)
        pdf_path = target_dir / f"{source.stem}_structural.pdf"
        render_newspaper_template_pdf(
            model=model,
            layout=layout,
            pdf_path=pdf_path,
        )
        return {
            "pdf_path": pdf_path,
            "structural_pdf_path": pdf_path,
            "facsimile_pdf_path": None,
            "clean_pdf_path": None,
            "layout_debug_path": None,
            "structural_debug_path": None,
            "structural_report_path": None,
            "search_text_path": None,
        }

    outputs = write_primary_outputs(
        source=image,
        target_dir=out_dir,
        engine_markdown=markdown,
        result=result,
        settings=settings,
        kind=InputKind.IMAGE,
        layout=layout,
        vl_json=vl if vl.is_file() else None,
        pdf_render_fn=_render_pdfs,
        newspaper_model=model,
    )

    assert outputs.markdown_path.is_file()
    assert outputs.structural_pdf_path is not None and outputs.structural_pdf_path.is_file()
    assert has_utf8_bom(outputs.markdown_path)
    assert outputs.facsimile_pdf_path is None
    assert list(out_dir.glob("*_test.pdf")) == []

    plan = resolve_pdf_output_plan(
        pdf_mode="structural",
        emit_facsimile=False,
        emit_clean=False,
        emit_debug_pdf=False,
    )
    assert plan.facsimile is False
