"""Tests for PP-StructureV3 parsing_res_list → document model."""

from __future__ import annotations

import json
from pathlib import Path

from kuvien_parsinta.layout.from_structure import (
    markdown_from_structure,
    structure_document_from_json,
    structure_document_from_parsing,
)
from kuvien_parsinta.ocr.structure import load_structure_json, normalize_parsing_blocks


def _koivisto_structure_json() -> Path | None:
    repo = Path(__file__).resolve().parents[2]
    candidates = [
        repo / "parsittavat" / "Koivisto_001" / "ocr" / "structure_test" / "koivisto2_0-1280x1280_res.json",
        repo / "parsittavat" / "Koivisto_001" / "ocr" / "koivisto2_0-1280x1280_res.json",
    ]
    for path in candidates:
        if path.is_file():
            payload = load_structure_json(path)
            if payload.get("parsing_res_list"):
                return path
    return None


def test_koivisto_structure_document_has_title_photo_and_columns() -> None:
    json_path = _koivisto_structure_json()
    if json_path is None:
        return

    document = structure_document_from_json(json_path)
    assert "Koivisto" in document.title
    assert "1280" not in document.title
    assert document.embedded_photo is not None
    assert document.is_multi_column
    assert any("Presidentti Mauno Koiviston" in p for block in document.blocks for p in block.paragraphs)


def test_koivisto_structure_markdown_is_text_only() -> None:
    json_path = _koivisto_structure_json()
    if json_path is None:
        return

    document = structure_document_from_json(json_path)
    md, uses_layout = markdown_from_structure(document, output_mode="auto")
    assert uses_layout is True
    assert "![" not in md
    assert "Koivisto" in md
    assert "Presidentti Mauno Koiviston" in md


def test_normalize_parsing_blocks_from_saved_json() -> None:
    json_path = _koivisto_structure_json()
    if json_path is None:
        return

    payload = load_structure_json(json_path)
    blocks = normalize_parsing_blocks(payload.get("parsing_res_list"))
    assert blocks
    document = structure_document_from_parsing(blocks, page_width=int(payload.get("width") or 1280))
    assert document.title
