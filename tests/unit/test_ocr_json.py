import json
from pathlib import Path

from kuvien_parsinta.ocr.image import _extract_ocr_from_data, _texts_from_json


def test_extract_top_level_rec_texts() -> None:
    data = {
        "rec_texts": ["Puolangan vuodeosasto", "lakkauttaminen"],
        "rec_scores": [0.98, 0.95],
    }
    texts, scores = _extract_ocr_from_data(data, [], [])
    assert texts == ["Puolangan vuodeosasto", "lakkauttaminen"]
    assert scores == [0.98, 0.95]


def test_extract_nested_overall_ocr_res() -> None:
    data = {
        "res": {
            "overall_ocr_res": {
                "rec_texts": ["Hello"],
                "rec_scores": [0.9],
            }
        }
    }
    texts, scores = _extract_ocr_from_data(data, [], [])
    assert texts == ["Hello"]
    assert scores == [0.9]


def test_texts_from_json_file(tmp_path: Path) -> None:
    json_path = tmp_path / "page_res.json"
    json_path.write_text(
        json.dumps({"rec_texts": ["A", "B"], "rec_scores": [0.8, 0.7]}),
        encoding="utf-8",
    )
    texts, scores = _texts_from_json(json_path, [], [])
    assert texts == ["A", "B"]
    assert scores == [0.8, 0.7]
