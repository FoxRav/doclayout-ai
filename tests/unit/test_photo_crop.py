"""Tests for embedded photo detection and cropping."""

from __future__ import annotations

from pathlib import Path

from kuvien_parsinta.layout.from_structure import structure_document_from_json, save_embedded_photo
from kuvien_parsinta.layout.photo_crop import crop_embedded_photo, detect_embedded_photo
from tests.unit.structure_fixtures import load_ocr_fixture, ocr_fields_from_fixture


def test_koivisto_detects_portrait_photo() -> None:
    repo = Path(__file__).resolve().parents[2]
    image_path = repo / "parsittavat" / "Koivisto_001" / "koivisto2_0-1280x1280.jpg"
    json_path = repo / "parsittavat" / "Koivisto_001" / "ocr" / "koivisto2_0-1280x1280_res.json"
    if not image_path.is_file() or not json_path.is_file():
        return

    document = structure_document_from_json(json_path)
    assert document.embedded_photo is not None
    assert 150 <= document.embedded_photo.x <= 220
    assert 400 <= document.embedded_photo.y <= 480
    assert 450 <= document.embedded_photo.width <= 600


def test_koivisto_crop_writes_photo_file(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    image_path = repo / "parsittavat" / "Koivisto_001" / "koivisto2_0-1280x1280.jpg"
    json_path = repo / "parsittavat" / "Koivisto_001" / "ocr" / "koivisto2_0-1280x1280_res.json"
    if not image_path.is_file() or not json_path.is_file():
        return

    document = structure_document_from_json(json_path)
    out = tmp_path / "photo.jpg"
    crop = save_embedded_photo(image_path=image_path, document=document, output_path=out)
    assert crop is not None
    assert out.is_file()
    assert out.stat().st_size > 10_000


def test_kuulutus_has_no_embedded_photo() -> None:
    repo = Path(__file__).resolve().parents[2]
    image_path = repo / "parsittavat" / "Kuulutus" / "kuulutus.jpg"
    data = load_ocr_fixture("kuulutus", subdir="Kuulutus")
    if image_path.is_file() and data is not None:
        texts, _scores, polys = ocr_fields_from_fixture(data)
        crop = detect_embedded_photo(image_path, polys)
        assert crop is None
        return
    if not image_path.is_file():
        return
    json_path = repo / "parsittavat" / "Kuulutus" / "ocr" / "kuulutus_res.json"
    if json_path.is_file():
        document = structure_document_from_json(json_path)
        assert document.embedded_photo is None
