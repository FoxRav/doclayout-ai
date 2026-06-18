"""PP-OCR for single images."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from kuvien_parsinta.encoding import fix_mojibake
from kuvien_parsinta.layout.structure import StructuredDocument, structure_document_from_ocr


@dataclass(frozen=True, slots=True)
class ImageOcrResult:
    texts: tuple[str, ...]
    scores: tuple[float, ...]
    polys: tuple[tuple[tuple[float, float], ...], ...]
    language: str
    raw_json_path: Path | None

    @property
    def confidence_avg(self) -> float:
        if not self.scores:
            return 0.0
        return sum(self.scores) / len(self.scores)

    @property
    def body_text(self) -> str:
        return fix_mojibake("\n".join(self.texts).strip())

    def flowing_markdown(self, *, title: str | None = None) -> str:
        from kuvien_parsinta.flow import ocr_to_flowing_markdown

        return ocr_to_flowing_markdown(texts=self.texts, polys=self.polys, title=title)

    def structured_markdown(self) -> str:
        from kuvien_parsinta.layout.structure import (
            structure_document_from_ocr,
            structured_to_markdown,
        )

        document = structure_document_from_ocr(texts=self.texts, polys=self.polys)
        return structured_to_markdown(document)

    def structured_document(self) -> StructuredDocument:
        return structure_document_from_ocr(texts=self.texts, polys=self.polys)


def run_image_ocr(
    *,
    image_path: Path,
    language: str,
    device: str,
    work_dir: Path,
) -> ImageOcrResult:
    """Run PaddleOCR on one image. Loads model once per call (CLI process)."""
    from paddleocr import PaddleOCR  # noqa: PLC0415

    work_dir.mkdir(parents=True, exist_ok=True)
    ocr = PaddleOCR(lang=language, device=device)
    results = ocr.predict(str(image_path))
    if not results:
        return ImageOcrResult(
            texts=(), scores=(), polys=(), language=language, raw_json_path=None
        )

    page = results[0]
    json_path = work_dir / f"{image_path.stem}_res.json"
    page.save_to_json(str(work_dir))

    texts: list[str] = []
    scores: list[float] = []
    polys: list[tuple[tuple[float, float], ...]] = []
    res = getattr(page, "res", None)
    if isinstance(res, dict):
        texts, scores = _extract_ocr_from_data(res, texts, scores)
        polys = _extract_polys_from_data(res, polys)

    if json_path.exists():
        texts, scores, polys = _fields_from_json(json_path, texts, scores, polys)

    return ImageOcrResult(
        texts=tuple(texts),
        scores=tuple(scores),
        polys=tuple(polys),
        language=language,
        raw_json_path=json_path if json_path.exists() else None,
    )


def _extract_ocr_from_data(
    data: dict[str, object],
    fallback_texts: list[str],
    fallback_scores: list[float],
) -> tuple[list[str], list[float]]:
    """Support PP-OCR predict JSON (top-level) and Structure nested formats."""
    rec_texts = data.get("rec_texts")
    rec_scores = data.get("rec_scores")
    if isinstance(rec_texts, list) and rec_texts:
        out_t = [str(t) for t in rec_texts]
        out_s = (
            [float(s) for s in rec_scores]
            if isinstance(rec_scores, list)
            else fallback_scores
        )
        return out_t, out_s

    res = data.get("res")
    if isinstance(res, dict):
        return _extract_ocr_from_data(res, fallback_texts, fallback_scores)

    ocr = data.get("overall_ocr_res")
    if isinstance(ocr, dict):
        return _extract_ocr_from_data(ocr, fallback_texts, fallback_scores)

    return fallback_texts, fallback_scores


def _poly_tuple(poly: object) -> tuple[tuple[float, float], ...]:
    if not isinstance(poly, list):
        return ()
    points: list[tuple[float, float]] = []
    for point in poly:
        if isinstance(point, list) and len(point) >= 2:
            points.append((float(point[0]), float(point[1])))
    return tuple(points)


def _extract_polys_from_data(
    data: dict[str, object],
    fallback_polys: list[tuple[tuple[float, float], ...]],
) -> list[tuple[tuple[float, float], ...]]:
    rec_polys = data.get("rec_polys")
    if isinstance(rec_polys, list) and rec_polys:
        return [_poly_tuple(poly) for poly in rec_polys]

    res = data.get("res")
    if isinstance(res, dict):
        return _extract_polys_from_data(res, fallback_polys)

    ocr = data.get("overall_ocr_res")
    if isinstance(ocr, dict):
        return _extract_polys_from_data(ocr, fallback_polys)

    return fallback_polys


def _fields_from_json(
    json_path: Path,
    fallback_texts: list[str],
    fallback_scores: list[float],
    fallback_polys: list[tuple[tuple[float, float], ...]],
) -> tuple[list[str], list[float], list[tuple[tuple[float, float], ...]]]:
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback_texts, fallback_scores, fallback_polys
    if not isinstance(data, dict):
        return fallback_texts, fallback_scores, fallback_polys
    texts, scores = _extract_ocr_from_data(data, fallback_texts, fallback_scores)
    polys = _extract_polys_from_data(data, fallback_polys)
    return texts, scores, polys


def _texts_from_json(
    json_path: Path,
    fallback_texts: list[str],
    fallback_scores: list[float],
) -> tuple[list[str], list[float]]:
    texts, scores, _polys = _fields_from_json(json_path, fallback_texts, fallback_scores, [])
    return texts, scores
