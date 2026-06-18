"""Layout merge helpers for VL + StructureV3 PDF rendering."""

from __future__ import annotations

from kuvien_parsinta.engines.layout_merge import (
    document_layout_is_sufficient,
    merge_vl_text_with_structure_layout,
    resolve_pdf_document,
)
from kuvien_parsinta.layout.photo_crop import CropRect
from kuvien_parsinta.layout.structure import LayoutBlockKind, StructuredBlock, StructuredDocument


def test_document_layout_insufficient_without_text_or_photo() -> None:
    doc = StructuredDocument(title="Asiakirja", blocks=())
    assert document_layout_is_sufficient(doc) is False


def test_document_layout_sufficient_with_photo() -> None:
    doc = StructuredDocument(
        title="Otsikko",
        blocks=(),
        embedded_photo=CropRect(x=10, y=10, width=100, height=100),
    )
    assert document_layout_is_sufficient(doc) is True


def test_resolve_pdf_uses_structure_helper_when_vl_lacks_layout() -> None:
    vl_doc = StructuredDocument(title="VL title", blocks=())
    structure_doc = StructuredDocument(
        title="Structure title",
        blocks=(
            StructuredBlock(
                kind=LayoutBlockKind.COLUMN,
                column_index=1,
                paragraphs=("Structure text",),
                y_min=100.0,
            ),
        ),
        embedded_photo=CropRect(x=5, y=5, width=50, height=50),
    )
    merged = resolve_pdf_document(
        vl_document=vl_doc,
        structure_document=structure_doc,
        vl_markdown="# VL title\n\nVL paragraph one.\n\nVL paragraph two.",
        use_structure_as_helper=True,
    )
    assert merged is not None
    assert merged.title == "VL title"
    assert merged.embedded_photo == structure_doc.embedded_photo
    assert any("VL paragraph" in p for block in merged.blocks for p in block.paragraphs)


def test_merge_vl_text_preserves_structure_columns() -> None:
    structure_doc = StructuredDocument(
        title="Old",
        blocks=(
            StructuredBlock(
                kind=LayoutBlockKind.COLUMN,
                column_index=0,
                paragraphs=("old left",),
                y_min=10.0,
            ),
            StructuredBlock(
                kind=LayoutBlockKind.COLUMN,
                column_index=1,
                paragraphs=("old right",),
                y_min=10.0,
            ),
        ),
    )
    merged = merge_vl_text_with_structure_layout(
        structure_doc,
        "# New title\n\nLeft text.\n\nRight text.",
    )
    assert merged.title == "New title"
    assert merged.blocks[0].paragraphs == ("Left text.",)
    assert merged.blocks[1].paragraphs == ("Right text.",)
