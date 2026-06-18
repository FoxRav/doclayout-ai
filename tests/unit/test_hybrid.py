"""Unit tests for hybrid merge logic."""

from __future__ import annotations

from pathlib import Path

from kuvien_parsinta.config import Settings
from kuvien_parsinta.engines.hybrid import merge_hybrid_outputs
from kuvien_parsinta.engines.paddleocr_vl_engine import VlEngineOutput
from kuvien_parsinta.engines.structurev3_engine import StructureV3Output
from kuvien_parsinta.fallback import ParseEngine
from kuvien_parsinta.layout.photo_crop import CropRect
from kuvien_parsinta.layout.structure import LayoutBlockKind, StructuredBlock, StructuredDocument
from kuvien_parsinta.models import OutputMode


def test_hybrid_uses_vl_text_and_structure_layout(tmp_path: Path) -> None:
    structure_doc = StructuredDocument(
        title="Old",
        blocks=(
            StructuredBlock(
                kind=LayoutBlockKind.FULL_WIDTH,
                column_index=None,
                paragraphs=("structure text",),
                y_min=0.0,
            ),
        ),
        embedded_photo=CropRect(x=5, y=5, width=20, height=20),
    )
    structure = StructureV3Output(
        markdown_text="# Old\n\nstructure text",
        confidence_avg=0.95,
        page_count=1,
        uses_layout_pdf=True,
        languages_tried=("fi",),
        structure_json_path=tmp_path / "ocr" / "s.json",
        document=structure_doc,
    )
    vl = VlEngineOutput(
        markdown_text="# New title\n\nVL paragraph.",
        confidence_avg=0.9,
        page_count=1,
        uses_layout_pdf=False,
        vl_json_path=tmp_path / "ocr" / "v.json",
        vl_markdown_path=tmp_path / "v.md",
    )

    result = merge_hybrid_outputs(
        source_stem="doc",
        target_dir=tmp_path,
        vl_out=vl,
        structure_out=structure,
        settings=Settings(),
        output_mode=OutputMode.FLOWING,
    )

    assert result.text_source == ParseEngine.PADDLE_VL.value
    assert result.layout_source == ParseEngine.PP_STRUCTURE.value
    assert "VL paragraph." in result.markdown_text
    assert result.pdf_document is not None
    assert result.pdf_document.embedded_photo == structure_doc.embedded_photo
    assert result.hybrid_json_path.is_file()
