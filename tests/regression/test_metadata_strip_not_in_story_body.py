"""Regression: metadata-strip text must not appear in story body."""

from __future__ import annotations

from pathlib import Path

from kuvien_parsinta.layout.newspaper_page_model import build_newspaper_page_model
from kuvien_parsinta.layout.page_layout_builder import build_page_layout
from kuvien_parsinta.markdown.newspaper_markdown import (
    extract_story_body,
    newspaper_model_to_markdown,
)


def test_metadata_strip_not_in_story_body() -> None:
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
    markdown = newspaper_model_to_markdown(model)
    body = extract_story_body(markdown).upper()
    sidebar = model.right_sidebar_text.upper()

    assert markdown.upper().count("1 MK") == 1
    assert markdown.upper().index("1 MK") < markdown.upper().index("# JO 39")
    assert "1 MK" not in body
    assert "(SIS." not in sidebar[:50]
    assert "***" not in body
    assert "☆" not in body
    assert "N:O 87" not in body
    assert "HUHTIKUUN" not in body
    assert "PNÄ" not in body
    assert not sidebar.strip().startswith("1 MK")
    assert "1 MK" in model.price_text.upper()
    assert len(model.ownership.reused_block_ids) == 0
    assert model.ownership.metadata_blocks_consumed_before_story is True
