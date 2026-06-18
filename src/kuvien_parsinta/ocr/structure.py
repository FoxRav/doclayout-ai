"""PP-StructureV3 layout parsing wrapper."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kuvien_parsinta.languages import structure_lang_for_paddle


@dataclass(frozen=True, slots=True)
class StructurePageResult:
    parsing_res_list: tuple[dict[str, Any], ...]
    overall_ocr_res: dict[str, Any]
    raw_json_path: Path
    page_index: int
    page_width: int
    page_height: int

    @property
    def confidence_avg(self) -> float:
        scores = self.overall_ocr_res.get("rec_scores")
        if not isinstance(scores, list) or not scores:
            return 0.0
        numeric = [float(score) for score in scores]
        return sum(numeric) / len(numeric)


@dataclass(frozen=True, slots=True)
class StructureParseResult:
    pages: tuple[StructurePageResult, ...]
    language: str

    @property
    def primary(self) -> StructurePageResult:
        return self.pages[0]

    @property
    def confidence_avg(self) -> float:
        if not self.pages:
            return 0.0
        return sum(page.confidence_avg for page in self.pages) / len(self.pages)


def run_structure_v3(
    *,
    input_path: Path,
    language: str,
    device: str,
    work_dir: Path,
) -> StructureParseResult:
    """Run PP-StructureV3 on an image or PDF and persist page JSON artefacts."""
    from paddleocr import PPStructureV3  # noqa: PLC0415

    work_dir.mkdir(parents=True, exist_ok=True)
    paddle_lang = structure_lang_for_paddle(language)
    pipeline = PPStructureV3(
        lang=paddle_lang,
        device=device,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_formula_recognition=False,
        use_table_recognition=False,
        use_chart_recognition=False,
    )
    raw_results = pipeline.predict(str(input_path))
    pages: list[StructurePageResult] = []
    multi_page = len(raw_results) > 1

    for page_index, result in enumerate(raw_results):
        if multi_page:
            json_path = work_dir / f"{page_index:03d}.res.json"
            result.save_to_json(save_path=str(work_dir))
            expected = work_dir / f"{page_index:03d}.res.json"
            if not expected.is_file():
                json_path = _find_saved_json(work_dir, page_index)
            else:
                json_path = expected
        else:
            result.save_to_json(save_path=str(work_dir))
            json_path = work_dir / f"{input_path.stem}_res.json"
            if not json_path.is_file():
                json_path = _find_saved_json(work_dir, page_index)

        payload = load_structure_json(json_path)
        parsing = normalize_parsing_blocks(payload.get("parsing_res_list"))
        ocr = payload.get("overall_ocr_res")
        if not isinstance(ocr, dict):
            ocr = {}
        pages.append(
            StructurePageResult(
                parsing_res_list=parsing,
                overall_ocr_res=ocr,
                raw_json_path=json_path,
                page_index=page_index,
                page_width=int(payload.get("width") or 0),
                page_height=int(payload.get("height") or 0),
            )
        )

    return StructureParseResult(pages=tuple(pages), language=language)


def load_structure_json(json_path: Path) -> dict[str, Any]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid structure JSON root in {json_path}")
    if isinstance(data.get("res"), dict):
        return data["res"]
    return data


def normalize_parsing_blocks(raw: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(raw, list):
        return ()
    blocks: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            blocks.append(item)
        elif hasattr(item, "to_dict"):
            converted = item.to_dict()
            if isinstance(converted, dict):
                blocks.append(converted)
    return tuple(blocks)


def _find_saved_json(work_dir: Path, page_index: int) -> Path:
    candidates = sorted(work_dir.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(f"StructureV3 did not write JSON under {work_dir}")
    if page_index < len(candidates):
        return candidates[page_index]
    return candidates[0]
