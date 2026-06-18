"""Tests for layout-aware document structuring."""

from __future__ import annotations

from pathlib import Path

from kuvien_parsinta.flow import layout_lines_from_ocr
from kuvien_parsinta.layout.from_structure import structure_document_from_json
from kuvien_parsinta.layout.structure import detect_multi_column, structured_to_markdown
from tests.unit.structure_fixtures import load_ocr_fixture, ocr_fields_from_fixture


def test_kuulutus_is_single_column() -> None:
    data = load_ocr_fixture("kuulutus", subdir="Kuulutus")
    if data is None:
        return
    texts, _scores, polys = ocr_fields_from_fixture(data)
    lines = layout_lines_from_ocr(texts, polys)
    assert detect_multi_column(lines) is False


def test_koivisto_detects_two_columns() -> None:
    json_path = _koivisto_json_path()
    if json_path is None:
        return
    document = structure_document_from_json(json_path)
    assert document.is_multi_column


def test_koivisto_structured_markdown_has_columns() -> None:
    json_path = _koivisto_json_path()
    if json_path is None:
        return
    document = structure_document_from_json(json_path)
    md = structured_to_markdown(document)

    assert document.is_multi_column
    assert "1280" not in document.title
    assert "Koivisto" in document.title
    assert "## Oikea palsta" in md
    assert "Presidentti Mauno Koiviston" in md


def _koivisto_json_path() -> Path | None:
    repo = Path(__file__).resolve().parents[2]
    primary = repo / "parsittavat" / "Koivisto_001" / "ocr" / "koivisto2_0-1280x1280_res.json"
    if primary.is_file() and load_ocr_fixture("koivisto2_0-1280x1280", subdir="Koivisto_001"):
        return primary
    fallback = (
        repo / "parsittavat" / "Koivisto_001" / "ocr" / "structure_test" / "koivisto2_0-1280x1280_res.json"
    )
    return fallback if fallback.is_file() else None
