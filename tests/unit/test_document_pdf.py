"""Tests for layout-faithful document PDF rendering."""

from __future__ import annotations

from pathlib import Path

from kuvien_parsinta.layout.from_structure import save_embedded_photo, structure_document_from_json
from kuvien_parsinta.pdf.document import render_document_pdf


def test_koivisto_layout_pdf_is_single_page(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    image_path = repo / "parsittavat" / "Koivisto_001" / "koivisto2_0-1280x1280.jpg"
    json_path = repo / "parsittavat" / "Koivisto_001" / "ocr" / "koivisto2_0-1280x1280_res.json"
    if not image_path.is_file() or not json_path.is_file():
        return

    document = structure_document_from_json(json_path, image_path=image_path)
    assert document.is_multi_column
    assert document.embedded_photo is not None

    pdf_path = tmp_path / "koivisto.pdf"
    photo_path = tmp_path / "photo.jpg"
    save_embedded_photo(image_path=image_path, document=document, output_path=photo_path)
    render_document_pdf(
        source_path=image_path,
        document=document,
        pdf_path=pdf_path,
        photo_crop_path=photo_path if photo_path.is_file() else None,
    )
    assert pdf_path.is_file()
    assert pdf_path.stat().st_size > 10_000
    assert b"/Count 1" in pdf_path.read_bytes()
