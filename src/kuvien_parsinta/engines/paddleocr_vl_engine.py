"""PaddleOCR-VL visual-language parse engine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from kuvien_parsinta.device import resolve_paddle_device
from kuvien_parsinta.encoding import fix_mojibake
from kuvien_parsinta.layout.from_structure import (
    markdown_from_structure,
    structure_document_from_parsing,
)
from kuvien_parsinta.layout.structure import StructuredDocument
from kuvien_parsinta.models import OutputMode, QualityMode
from kuvien_parsinta.ocr.structure import load_structure_json, normalize_parsing_blocks

logger = structlog.get_logger(__name__)


class VlNotInstalledError(ImportError):
    """Raised when PaddleOCR-VL extras are missing."""


@dataclass(frozen=True, slots=True)
class VlEngineOutput:
    markdown_text: str
    confidence_avg: float
    page_count: int
    uses_layout_pdf: bool
    vl_json_path: Path
    vl_markdown_path: Path
    document: StructuredDocument | None = None


def run_paddleocr_vl(
    *,
    input_path: Path,
    target_dir: Path,
    pipeline_version: str,
    device: str,
    save_raw: bool,
    output_mode: OutputMode,
    quality: QualityMode = QualityMode.STANDARD,
) -> VlEngineOutput:
    """Run PaddleOCR-VL, persist raw artefacts, return normalized output."""
    PaddleOCRVL = _load_paddleocr_vl_class()
    work_dir = target_dir / "ocr"
    work_dir.mkdir(parents=True, exist_ok=True)

    resolved_device = resolve_paddle_device(device)
    logger.info(
        "paddleocr_vl_start",
        input=str(input_path),
        pipeline_version=pipeline_version,
        device=resolved_device,
    )

    use_orientation = quality is QualityMode.MAX
    use_unwarping = quality is QualityMode.MAX

    pipeline = PaddleOCRVL(
        pipeline_version=pipeline_version,
        device=resolved_device,
        use_doc_orientation_classify=use_orientation,
        use_doc_unwarping=use_unwarping,
    )
    raw_results = pipeline.predict(str(input_path))
    if not raw_results:
        raise RuntimeError("PaddleOCR-VL returned no pages")

    page_results: list[dict[str, Any]] = []
    markdown_parts: list[str] = []
    confidence_values: list[float] = []

    for page_index, result in enumerate(raw_results):
        json_path = _save_vl_json(
            result=result,
            work_dir=work_dir,
            stem=input_path.stem,
            page_index=page_index,
            multi_page=len(raw_results) > 1,
            save_raw=save_raw,
        )
        payload = load_structure_json(json_path)
        page_results.append(payload)
        markdown_parts.append(_markdown_from_vl_payload(result, payload))
        confidence_values.append(_confidence_from_payload(payload))

    markdown_text = fix_mojibake("\n\n".join(part for part in markdown_parts if part.strip()).strip())
    if not markdown_text:
        raise RuntimeError("PaddleOCR-VL produced empty markdown")

    primary_json = work_dir / f"{input_path.stem}_vl_res.json"
    if not primary_json.is_file() and page_results:
        primary_json = _primary_vl_json_path(work_dir, input_path.stem, len(raw_results))

    vl_md_path = target_dir / f"{input_path.stem}_vl.md"
    vl_md_path.write_text(markdown_text + "\n", encoding="utf-8")

    document = _document_from_vl_payload(page_results[0], image_path=input_path)
    if document is not None:
        md_content, uses_layout_pdf = markdown_from_structure(
            document,
            output_mode=output_mode.value,
        )
        if md_content.strip():
            markdown_text = md_content
            uses_layout = uses_layout_pdf
        else:
            uses_layout = False
    else:
        uses_layout = False

    confidence_avg = sum(confidence_values) / len(confidence_values) if confidence_values else 0.75

    logger.info(
        "paddleocr_vl_done",
        pages=len(raw_results),
        json=str(primary_json),
        vl_md=str(vl_md_path),
        confidence=confidence_avg,
    )

    return VlEngineOutput(
        markdown_text=markdown_text,
        confidence_avg=confidence_avg,
        page_count=len(raw_results),
        uses_layout_pdf=uses_layout,
        vl_json_path=primary_json,
        vl_markdown_path=vl_md_path,
        document=document,
    )


def _load_paddleocr_vl_class() -> type[Any]:
    try:
        from paddleocr import PaddleOCRVL  # noqa: PLC0415
    except ImportError as exc:
        raise VlNotInstalledError(
            "PaddleOCR-VL is not installed. Run: "
            "powershell -ExecutionPolicy Bypass -File scripts\\install_paddleocr_vl.ps1"
        ) from exc
    return PaddleOCRVL


def _save_vl_json(
    *,
    result: object,
    work_dir: Path,
    stem: str,
    page_index: int,
    multi_page: bool,
    save_raw: bool,
) -> Path:
    if not save_raw:
        save_raw = True
    save_to_json = getattr(result, "save_to_json", None)
    if not callable(save_to_json):
        raise RuntimeError("PaddleOCR-VL result missing save_to_json()")

    save_to_json(save_path=str(work_dir))
    if multi_page:
        candidate = work_dir / f"{page_index:03d}.res.json"
        target = work_dir / f"{page_index:03d}_vl.res.json"
    else:
        candidate = work_dir / f"{stem}_res.json"
        target = work_dir / f"{stem}_vl_res.json"

    if candidate.is_file() and candidate != target:
        target.write_text(candidate.read_text(encoding="utf-8"), encoding="utf-8")
        if not candidate.name.endswith("_vl_res.json"):
            candidate.unlink(missing_ok=True)
    elif not target.is_file():
        json_files = sorted(work_dir.glob("*.json"))
        if page_index < len(json_files):
            target.write_text(json_files[page_index].read_text(encoding="utf-8"), encoding="utf-8")

    if not target.is_file():
        raise RuntimeError(f"PaddleOCR-VL did not write JSON to {work_dir}")
    return target


def _primary_vl_json_path(work_dir: Path, stem: str, page_count: int) -> Path:
    single = work_dir / f"{stem}_vl_res.json"
    if single.is_file():
        return single
    if page_count == 1:
        return work_dir / f"{stem}_vl_res.json"
    return work_dir / "000_vl.res.json"


def _markdown_from_vl_payload(result: object, payload: dict[str, Any]) -> str:
    markdown_attr = getattr(result, "markdown", None)
    if isinstance(markdown_attr, dict):
        texts = markdown_attr.get("markdown_texts")
        if isinstance(texts, str) and texts.strip():
            return fix_mojibake(texts.strip())
        if isinstance(texts, list):
            joined = "\n\n".join(str(item).strip() for item in texts if str(item).strip())
            if joined:
                return fix_mojibake(joined)

    parsing = normalize_parsing_blocks(payload.get("parsing_res_list"))
    if parsing:
        blocks = [
            str(block.get("block_content", "")).strip()
            for block in parsing
            if isinstance(block, dict)
            and block.get("block_label") not in {"header", "footer", "number", "image", "figure"}
            and str(block.get("block_content", "")).strip()
        ]
        if blocks:
            return fix_mojibake("\n\n".join(blocks))

    save_md = getattr(result, "save_to_markdown", None)
    if callable(save_md):
        tmp_dir = Path(payload.get("input_path", "page")).parent
        if not isinstance(tmp_dir, Path):
            tmp_dir = Path(".")
        save_md(save_path=str(tmp_dir))
    return ""


def _confidence_from_payload(payload: dict[str, Any]) -> float:
    ocr = payload.get("overall_ocr_res")
    if isinstance(ocr, dict):
        scores = ocr.get("rec_scores")
        if isinstance(scores, list) and scores:
            numeric = [float(score) for score in scores]
            return sum(numeric) / len(numeric)
    parsing = payload.get("parsing_res_list")
    if isinstance(parsing, list) and parsing:
        return 0.85
    return 0.0


def _document_from_vl_payload(
    payload: dict[str, Any],
    *,
    image_path: Path,
) -> StructuredDocument | None:
    parsing = normalize_parsing_blocks(payload.get("parsing_res_list"))
    if not parsing:
        return None
    page_width = int(payload.get("width") or 0)
    return structure_document_from_parsing(
        parsing,
        image_path=image_path,
        page_width=page_width,
    )
