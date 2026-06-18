"""PP-StructureV3 parse engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kuvien_parsinta.layout.from_structure import (
    markdown_from_structure,
    structure_document_from_parsing,
)
from kuvien_parsinta.layout.structure import StructuredDocument
from kuvien_parsinta.models import OutputMode, QualityMode
from kuvien_parsinta.ocr.structure import run_structure_v3


@dataclass(frozen=True, slots=True)
class StructureV3Output:
    markdown_text: str
    confidence_avg: float
    page_count: int
    uses_layout_pdf: bool
    languages_tried: tuple[str, ...]
    structure_json_path: Path
    document: StructuredDocument


def run_structurev3(
    *,
    source: Path,
    target_dir: Path,
    priority: tuple[str, ...],
    device: str,
    output_mode: OutputMode,
    confidence_threshold: float,
    quality: QualityMode = QualityMode.STANDARD,
) -> StructureV3Output:
    """Run StructureV3 and build markdown from parsing_res_list."""
    best_conf = 0.0
    best_page = None
    best_parsed = None
    languages_tried: list[str] = []

    for lang in priority:
        languages_tried.append(lang)
        parsed = run_structure_v3(
            input_path=source,
            language=lang,
            device=device,
            work_dir=target_dir / "ocr",
        )
        page = parsed.primary
        if page.confidence_avg >= best_conf:
            best_conf = page.confidence_avg
            best_page = page
            best_parsed = parsed
        if quality is not QualityMode.MAX and page.confidence_avg >= confidence_threshold:
            break

    if best_page is None or best_parsed is None:
        raise RuntimeError("StructureV3 produced no OCR pages")

    document = structure_document_from_parsing(
        best_page.parsing_res_list,
        image_path=source,
        page_width=best_page.page_width,
    )
    md_content, uses_layout_pdf = markdown_from_structure(
        document,
        output_mode=output_mode.value,
    )
    if not md_content.strip():
        raise RuntimeError("StructureV3 produced empty markdown")

    return StructureV3Output(
        markdown_text=md_content,
        confidence_avg=best_conf,
        page_count=len(best_parsed.pages),
        uses_layout_pdf=uses_layout_pdf,
        languages_tried=tuple(languages_tried),
        structure_json_path=best_page.raw_json_path,
        document=document,
    )
