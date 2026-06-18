"""Engine fallback rules (Structure → VL, low-confidence retry)."""

from __future__ import annotations

from enum import Enum

from kuvien_parsinta.layout.structure import StructuredDocument


class ParseEngine(str, Enum):
    NATIVE_PDF = "native_pdf"
    PP_OCR_IMAGE = "pp_ocr_image"
    PP_STRUCTURE = "pp_structure"
    PADDLE_VL = "paddle_vl"
    HYBRID = "hybrid"


def should_fallback_to_vl(
    *,
    ocr_confidence_avg: float,
    low_confidence_pages: tuple[int, ...],
    page_count: int,
    threshold: float = 0.6,
    low_ratio: float = 0.2,
) -> bool:
    """True when document warrants PaddleOCR-VL re-processing."""
    if page_count == 0:
        return False
    if ocr_confidence_avg < threshold:
        return True
    return len(low_confidence_pages) / page_count > low_ratio


def structure_result_is_weak(
    *,
    confidence_avg: float,
    document: StructuredDocument,
    threshold: float,
) -> bool:
    """Heuristic: StructureV3 output may benefit from VL re-parse."""
    if confidence_avg < threshold:
        return True
    title = document.title.strip()
    if not title or title == "Asiakirja":
        return True
    has_text = any(
        paragraph.strip()
        for block in document.blocks
        for paragraph in block.paragraphs
    )
    if not has_text and document.embedded_photo is None:
        return True
    return False
