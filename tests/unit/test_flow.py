"""Tests for OCR flowing text reflow."""

from __future__ import annotations

import json
from pathlib import Path

from kuvien_parsinta.flow import (
    dehyphenate_lines,
    extract_title,
    flowing_text_from_lines,
    layout_lines_from_ocr,
    ocr_to_flowing_markdown,
)


def test_dehyphenate_merges_line_break_hyphens() -> None:
    lines = layout_lines_from_ocr(
        ["Kaikenlainen joutilaana sei-", "soskeleminen teitten risteyksessä"],
        None,
    )
    merged = dehyphenate_lines(lines)
    assert len(merged) == 1
    assert merged[0].text == "Kaikenlainen joutilaana seisoskeleminen teitten risteyksessä"


def test_kuulutus_flowing_markdown(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    json_path = repo / "parsittavat" / "Kuulutus" / "ocr" / "kuulutus_res.json"
    if not json_path.is_file():
        return
    data = json.loads(json_path.read_text(encoding="utf-8"))
    md = ocr_to_flowing_markdown(
        texts=data["rec_texts"],
        polys=data["rec_polys"],
    )
    assert "# Kaikenlainen joutilaana seisoskeleminen teitten risteyksessä" in md
    assert "sei-\n" not in md
    assert "seisoskeleminen teitten risteyksessä" in md
    assert "portintienoilla" in md
    assert "Ikaalisissa, Tammikuun 23 päivana 1916" in md
    assert "**KAARLO SPARFVÉN.**" in md
    assert md.count("\n\n") >= 2


def test_flowing_text_splits_signature_and_dateline() -> None:
    lines = layout_lines_from_ocr(
        [
            "Ensimmäinen kappale joka on merkittä-",
            "vä.",
            "Kaupungissa, Tammikuun 1 päivänä 1900",
            "MIKAEL MEINANDER.",
        ],
        None,
    )
    body, dateline, signature = flowing_text_from_lines(lines)
    assert body == ["Ensimmäinen kappale joka on merkittävä."]
    assert dateline == "Kaupungissa, Tammikuun 1 päivänä 1900"
    assert signature == "MIKAEL MEINANDER."


def test_laho_headline_title_from_ocr_not_filename() -> None:
    repo = Path(__file__).resolve().parents[2]
    json_path = repo / "parsittavat" / "lattiasienet" / "ocr" / "laho-1280x1280_res.json"
    if not json_path.is_file():
        return
    data = json.loads(json_path.read_text(encoding="utf-8"))
    lines = layout_lines_from_ocr(data["rec_texts"], data["rec_polys"])
    title, _remaining = extract_title(lines)
    assert "1280" not in title
    assert "laho-1280" not in title.lower()
    assert "Sadat" in title
    assert "selvitetty" in title
