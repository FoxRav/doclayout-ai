"""Engine selection and hybrid pipeline behaviour."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from kuvien_parsinta.config import Settings
from kuvien_parsinta.engines.hybrid import merge_hybrid_outputs
from kuvien_parsinta.engines.paddleocr_vl_engine import VlEngineOutput
from kuvien_parsinta.engines.runner import (
    EngineRunError,
    resolve_engine_choice,
    run_parse_engines,
)
from kuvien_parsinta.engines.structurev3_engine import StructureV3Output
from kuvien_parsinta.fallback import ParseEngine
from kuvien_parsinta.layout.structure import LayoutBlockKind, StructuredBlock, StructuredDocument
from kuvien_parsinta.models import OutputMode, ParseEngineChoice


def test_resolve_engine_default_is_hybrid() -> None:
    assert (
        resolve_engine_choice(
            cli_engine=None,
            settings_engine=ParseEngineChoice.HYBRID,
        )
        is ParseEngineChoice.HYBRID
    )


def test_resolve_engine_auto_maps_to_hybrid() -> None:
    assert (
        resolve_engine_choice(
            cli_engine=None,
            settings_engine=ParseEngineChoice.AUTO,
            speed_priority=False,
        )
        is ParseEngineChoice.HYBRID
    )


def test_run_structurev3_only_no_vl(tmp_path: Path) -> None:
    source = tmp_path / "doc.jpg"
    source.write_bytes(b"fake")
    target = tmp_path / "out"
    target.mkdir()

    structure = StructureV3Output(
        markdown_text="# Title\n\nBody",
        confidence_avg=0.95,
        page_count=1,
        uses_layout_pdf=False,
        languages_tried=("fi",),
        structure_json_path=target / "ocr" / "doc_res.json",
        document=StructuredDocument(title="Title", blocks=()),
    )
    settings = Settings(vl_enabled=True)

    with (
        patch(
            "kuvien_parsinta.engines.runner.run_structurev3",
            return_value=structure,
        ),
        patch("kuvien_parsinta.engines.runner.run_paddleocr_vl") as mock_vl,
    ):
        output = run_parse_engines(
            source=source,
            target_dir=target,
            settings=settings,
            output_mode=OutputMode.FLOWING,
            engine_choice=ParseEngineChoice.STRUCTUREV3,
        )

    mock_vl.assert_not_called()
    assert output.engine is ParseEngine.PP_STRUCTURE


def test_hybrid_merges_vl_text_and_structure_layout(tmp_path: Path) -> None:
    source = tmp_path / "doc.jpg"
    source.write_bytes(b"fake")
    target = tmp_path / "out"
    ocr = target / "ocr"
    ocr.mkdir(parents=True)

    from kuvien_parsinta.layout.photo_crop import CropRect

    structure_doc = StructuredDocument(
        title="Structure title",
        blocks=(
            StructuredBlock(
                kind=LayoutBlockKind.COLUMN,
                column_index=1,
                paragraphs=("Old text",),
                y_min=10.0,
            ),
        ),
        embedded_photo=CropRect(x=1, y=2, width=10, height=10),
    )
    structure = StructureV3Output(
        markdown_text="# Structure title\n\nOld text",
        confidence_avg=0.99,
        page_count=1,
        uses_layout_pdf=True,
        languages_tried=("fi",),
        structure_json_path=ocr / "doc_res.json",
        document=structure_doc,
    )
    structure.structure_json_path.write_text("{}", encoding="utf-8")

    vl_out = VlEngineOutput(
        markdown_text="# VL title\n\nVL paragraph.",
        confidence_avg=0.88,
        page_count=1,
        uses_layout_pdf=False,
        vl_json_path=ocr / "doc_vl_res.json",
        vl_markdown_path=target / "doc_vl.md",
        document=None,
    )

    settings = Settings()

    with (
        patch(
            "kuvien_parsinta.engines.runner.run_structurev3",
            return_value=structure,
        ),
        patch("kuvien_parsinta.engines.runner._try_vl", return_value=vl_out),
    ):
        output = run_parse_engines(
            source=source,
            target_dir=target,
            settings=settings,
            output_mode=OutputMode.FLOWING,
            engine_choice=ParseEngineChoice.HYBRID,
        )

    assert output.engine is ParseEngine.HYBRID
    assert "VL paragraph." in output.markdown_text
    assert output.document is not None
    assert output.document.embedded_photo == structure_doc.embedded_photo
    assert output.hybrid_json_path is not None
    assert output.hybrid_json_path.is_file()


def test_hybrid_detects_title_conflict() -> None:
    structure = StructureV3Output(
        markdown_text="# Structure\n\nBody",
        confidence_avg=0.9,
        page_count=1,
        uses_layout_pdf=False,
        languages_tried=("fi",),
        structure_json_path=Path("ocr/doc_res.json"),
        document=StructuredDocument(title="Structure", blocks=()),
    )
    vl_out = VlEngineOutput(
        markdown_text="# Different\n\nBody",
        confidence_avg=0.9,
        page_count=1,
        uses_layout_pdf=False,
        vl_json_path=Path("ocr/doc_vl_res.json"),
        vl_markdown_path=Path("doc_vl.md"),
    )
    merged = merge_hybrid_outputs(
        source_stem="doc",
        target_dir=Path("out"),
        vl_out=vl_out,
        structure_out=structure,
        settings=Settings(),
        output_mode=OutputMode.FLOWING,
    )
    assert any(c["type"] == "title" for c in merged.conflicts)


def test_vl_fails_fallback_structurev3_with_metadata(tmp_path: Path) -> None:
    source = tmp_path / "doc.jpg"
    source.write_bytes(b"fake")
    target = tmp_path / "out"
    target.mkdir()

    structure = StructureV3Output(
        markdown_text="# Fallback\n\nText",
        confidence_avg=0.88,
        page_count=1,
        uses_layout_pdf=False,
        languages_tried=("fi",),
        structure_json_path=target / "ocr" / "doc_res.json",
        document=StructuredDocument(title="Fallback", blocks=()),
    )
    settings = Settings(vl_enabled=True, vl_fallback_on_error=True)

    with (
        patch(
            "kuvien_parsinta.engines.runner.run_paddleocr_vl",
            side_effect=RuntimeError("VL model missing"),
        ),
        patch(
            "kuvien_parsinta.engines.runner.run_structurev3",
            return_value=structure,
        ),
    ):
        output = run_parse_engines(
            source=source,
            target_dir=target,
            settings=settings,
            output_mode=OutputMode.FLOWING,
            engine_choice=ParseEngineChoice.VL,
        )

    assert output.fallback_used is True
    assert output.primary_engine == ParseEngine.PADDLE_VL.value


def test_best_mode_produces_hybrid_and_compare_report(tmp_path: Path) -> None:
    source = tmp_path / "doc.jpg"
    source.write_bytes(b"fake")
    target = tmp_path / "out"
    ocr = target / "ocr"
    ocr.mkdir(parents=True)

    structure = StructureV3Output(
        markdown_text="# S\n\nBody",
        confidence_avg=0.99,
        page_count=1,
        uses_layout_pdf=True,
        languages_tried=("fi",),
        structure_json_path=ocr / "doc_res.json",
        document=StructuredDocument(title="S", blocks=()),
    )
    structure.structure_json_path.write_text("{}", encoding="utf-8")

    vl_out = VlEngineOutput(
        markdown_text="# VL\n\nVL body",
        confidence_avg=0.85,
        page_count=1,
        uses_layout_pdf=False,
        vl_json_path=ocr / "doc_vl_res.json",
        vl_markdown_path=target / "doc_vl.md",
        document=None,
    )

    settings = Settings(vl_enabled=True, save_engine_comparison=True)

    with (
        patch(
            "kuvien_parsinta.engines.runner.run_structurev3",
            return_value=structure,
        ),
        patch("kuvien_parsinta.engines.runner._try_vl", return_value=vl_out),
    ):
        output = run_parse_engines(
            source=source,
            target_dir=target,
            settings=settings,
            output_mode=OutputMode.FLOWING,
            engine_choice=ParseEngineChoice.BEST,
        )

    assert output.engine is ParseEngine.HYBRID
    assert output.compare_report_path is not None
    report = json.loads(output.compare_report_path.read_text(encoding="utf-8"))
    assert report["selected_engine"] == ParseEngine.HYBRID.value
    assert (ocr / "doc_structurev3_res.json").is_file()
    assert (ocr / "doc_hybrid_res.json").is_file()


def test_hybrid_both_fail_raises(tmp_path: Path) -> None:
    source = tmp_path / "doc.jpg"
    source.write_bytes(b"fake")
    target = tmp_path / "out"
    settings = Settings(vl_enabled=True)

    with (
        patch(
            "kuvien_parsinta.engines.runner._try_vl",
            return_value=None,
        ),
        patch(
            "kuvien_parsinta.engines.runner._try_structure",
            return_value=None,
        ),
    ):
        with pytest.raises(EngineRunError):
            run_parse_engines(
                source=source,
                target_dir=target,
                settings=settings,
                output_mode=OutputMode.AUTO,
                engine_choice=ParseEngineChoice.HYBRID,
            )
