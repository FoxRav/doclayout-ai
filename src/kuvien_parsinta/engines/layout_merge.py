"""Merge VL text with StructureV3 layout for PDF rendering."""

from __future__ import annotations

import re

from kuvien_parsinta.layout.structure import (
    LayoutBlockKind,
    StructuredBlock,
    StructuredDocument,
)

_COLUMN_HEADING_RE = re.compile(r"^##\s+(Oikea|Vasen)\s+palsta\s*$", re.IGNORECASE | re.MULTILINE)


def document_layout_is_sufficient(document: StructuredDocument | None) -> bool:
    """True when VL/Structure document has enough geometry for layout PDF."""
    if document is None:
        return False
    has_text = any(
        paragraph.strip()
        for block in document.blocks
        for paragraph in block.paragraphs
    )
    if has_text:
        return True
    return document.embedded_photo is not None and document.title.strip() not in ("", "Asiakirja")


def resolve_pdf_document(
    *,
    vl_document: StructuredDocument | None,
    structure_document: StructuredDocument | None,
    vl_markdown: str,
    use_structure_as_helper: bool,
) -> StructuredDocument | None:
    """Pick document for layout PDF: VL first, StructureV3 as layout helper."""
    if document_layout_is_sufficient(vl_document):
        return vl_document
    if not use_structure_as_helper or structure_document is None:
        return vl_document
    if not document_layout_is_sufficient(structure_document):
        return vl_document
    return merge_vl_text_with_structure_layout(structure_document, vl_markdown)


def merge_vl_text_with_structure_layout(
    structure_doc: StructuredDocument,
    vl_markdown: str,
) -> StructuredDocument:
    """Keep StructureV3 geometry; inject VL markdown as body text."""
    title = _title_from_markdown(vl_markdown) or structure_doc.title
    paragraphs = _body_paragraphs_from_markdown(vl_markdown)
    if not paragraphs:
        return StructuredDocument(
            title=title,
            blocks=structure_doc.blocks,
            embedded_photo=structure_doc.embedded_photo,
        )

    text_kinds = frozenset({LayoutBlockKind.COLUMN, LayoutBlockKind.FULL_WIDTH})
    text_blocks = [block for block in structure_doc.blocks if block.kind in text_kinds]
    if not text_blocks:
        return StructuredDocument(
            title=title,
            blocks=structure_doc.blocks,
            embedded_photo=structure_doc.embedded_photo,
        )

    new_blocks: list[StructuredBlock] = []
    para_idx = 0
    for block in structure_doc.blocks:
        if block.kind not in text_kinds:
            new_blocks.append(block)
            continue
        if para_idx >= len(paragraphs):
            new_blocks.append(block)
            continue
        new_blocks.append(
            StructuredBlock(
                kind=block.kind,
                column_index=block.column_index,
                paragraphs=(paragraphs[para_idx],),
                y_min=block.y_min,
            )
        )
        para_idx += 1

    while para_idx < len(paragraphs):
        last = new_blocks[-1] if new_blocks else None
        if last is not None and last.kind in text_kinds:
            merged = last.paragraphs + (paragraphs[para_idx],)
            new_blocks[-1] = StructuredBlock(
                kind=last.kind,
                column_index=last.column_index,
                paragraphs=merged,
                y_min=last.y_min,
            )
        else:
            new_blocks.append(
                StructuredBlock(
                    kind=LayoutBlockKind.FULL_WIDTH,
                    column_index=None,
                    paragraphs=(paragraphs[para_idx],),
                    y_min=0.0,
                )
            )
        para_idx += 1

    return StructuredDocument(
        title=title,
        blocks=tuple(new_blocks),
        embedded_photo=structure_doc.embedded_photo,
    )


def _title_from_markdown(markdown: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip()
    return ""


def _body_paragraphs_from_markdown(markdown: str) -> tuple[str, ...]:
    body_lines: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            continue
        if _COLUMN_HEADING_RE.match(stripped):
            continue
        body_lines.append(line)
    text = "\n".join(body_lines)
    parts = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    return tuple(parts)
