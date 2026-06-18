"""Shared helpers for tests reading StructureV3 JSON artefacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kuvien_parsinta.ocr.structure import load_structure_json


def load_ocr_fixture(stem: str, *, subdir: str) -> dict[str, Any] | None:
    repo = Path(__file__).resolve().parents[2]
    json_path = repo / "parsittavat" / subdir / "ocr" / f"{stem}_res.json"
    if not json_path.is_file():
        return None
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and data.get("parsing_res_list"):
        return data
    if isinstance(data.get("res"), dict) and data["res"].get("parsing_res_list"):
        return data["res"]
    return None


def ocr_fields_from_fixture(data: dict[str, Any]) -> tuple[list[str], list[float], list[list[list[float]]]]:
    ocr = data.get("overall_ocr_res")
    if not isinstance(ocr, dict):
        return [], [], []
    texts = ocr.get("rec_texts")
    scores = ocr.get("rec_scores")
    polys = ocr.get("rec_polys")
    out_texts = [str(t) for t in texts] if isinstance(texts, list) else []
    out_scores = [float(s) for s in scores] if isinstance(scores, list) else []
    out_polys: list[list[list[float]]] = []
    if isinstance(polys, list):
        for poly in polys:
            if isinstance(poly, list):
                out_polys.append(poly)
    return out_texts, out_scores, out_polys
