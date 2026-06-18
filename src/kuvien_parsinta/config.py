"""Application settings."""

from __future__ import annotations

from functools import lru_cache

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from kuvien_parsinta.device import configure_cuda_runtime, resolve_paddle_device
from kuvien_parsinta.languages import (
    DEFAULT_LANGUAGE_PRIORITY,
    OcrLanguageMode,
    PRIMARY_LANGUAGE,
)
from kuvien_parsinta.models import OutputMode, ParseEngineChoice, PdfMode, QualityMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PARSE_", env_file=".env", extra="ignore")

    engine: ParseEngineChoice = Field(
        default=ParseEngineChoice.HYBRID,
        description="Default engine: hybrid|vl|structurev3|best|auto",
    )
    quality: QualityMode = Field(
        default=QualityMode.MAX,
        description="Parse quality: standard or max (slower, higher fidelity)",
    )
    speed_priority: bool = Field(
        default=False,
        description="When true, auto selects structurev3 instead of hybrid",
    )
    structurev3_enabled: bool = Field(default=True)
    vl_enabled: bool = Field(default=True)
    use_vl_for_text: bool = Field(default=True)
    use_vl_for_reading_order: bool = Field(default=True)
    use_structurev3_for_layout: bool = Field(default=True)
    use_structurev3_for_images: bool = Field(default=True)
    use_structurev3_for_pdf_geometry: bool = Field(default=True)
    save_engine_comparison: bool = Field(default=True)
    no_silent_fallback: bool = Field(default=True)
    pdf_mode: PdfMode = Field(default=PdfMode.STRUCTURAL)
    layout_preserve: bool = Field(default=True)
    reflow_text: bool = Field(default=False)
    facsimile_visible_ocr: bool = Field(
        default=False,
        description="When true, draw visible OCR on facsimile (must stay false for archive PDFs)",
    )
    facsimile_invisible_text: bool = Field(
        default=True,
        description="Embed searchable invisible OCR text layer in facsimile PDFs",
    )
    facsimile_draw_debug: bool = Field(
        default=False,
        description="Draw debug overlays on facsimile PDF (use ocr_overlay_debug.pdf instead)",
    )
    facsimile_draw_bbox: bool = Field(
        default=False,
        description="Draw bbox rectangles on facsimile PDF (use ocr_overlay_debug.pdf instead)",
    )
    ocr_device: str = Field(
        default="auto",
        description="Paddle device: auto (prefer GPU), gpu:0, cpu, …",
    )
    ocr_language_mode: OcrLanguageMode = Field(default=OcrLanguageMode.AUTO)
    ocr_primary_language: str = Field(default=PRIMARY_LANGUAGE)
    ocr_extra_languages: str = Field(
        default=",".join(DEFAULT_LANGUAGE_PRIORITY[1:]),
        description="Comma-separated ISO codes after primary (e.g. sv,en,de)",
    )
    ocr_vl_confidence_threshold: float = Field(default=0.6)
    vl_pipeline_version: str = Field(default="v1.6")
    vl_device: str = Field(default="auto")
    vl_save_raw: bool = Field(default=True)
    vl_fallback_on_error: bool = Field(default=True)
    default_output_mode: OutputMode = Field(default=OutputMode.AUTO)
    write_pdf: bool = Field(default=True)
    emit_facsimile: bool = Field(
        default=False,
        description="Write optional archive facsimile to ocr/<name>_facsimile.pdf",
    )
    emit_clean: bool = Field(
        default=False,
        description="Write optional reflowed clean PDF to <name>_clean.pdf",
    )
    emit_debug_pdf: bool = Field(
        default=False,
        description="Write debug PDFs under debug_output_dir (overlay + search layer)",
    )
    emit_test_artifacts: bool = Field(
        default=False,
        description="Allow test-only artefacts in production runs (must stay false)",
    )
    debug_output_dir: str = Field(
        default="ocr",
        description="Subdirectory under output dir for QA/debug artefacts",
    )
    render_text_as_image: bool = Field(
        default=False,
        description="When true, render text regions as raster crops (must stay false for structural PDF)",
    )
    render_masthead_as_text: bool = Field(
        default=True,
        description="Render masthead label as PDF text, never as image crop",
    )
    render_newspaper_name_as_text: bool = Field(
        default=True,
        description="Render newspaper name as PDF text, never as image crop",
    )
    allow_text_crops: bool = Field(
        default=False,
        description="Allow embedding OCR text regions as raster crops in structural PDF",
    )
    allow_photo_crops: bool = Field(
        default=True,
        description="Allow hero/article photo crops in structural PDF",
    )
    newspaper_compact: bool = Field(default=True)
    vertical_gap_scale: float = Field(default=0.45)
    headline_to_image_gap_ratio: float = Field(default=0.018)
    image_to_caption_gap_ratio: float = Field(default=0.004)
    caption_to_lower_headline_gap_ratio: float = Field(default=0.015)
    lower_headline_to_columns_gap_ratio: float = Field(default=0.010)
    bottom_column_min_font_size: float = Field(default=5.5)
    body_min_font_size: float = Field(default=6.0)
    allow_text_overflow_report: bool = Field(default=True)
    structural_page_scale: str = Field(default="large")
    structural_margin_ratio: float = Field(default=0.035)
    structural_compact_vertical: bool = Field(default=True)

    def debug_dir(self, target_dir: Path) -> Path:
        name = self.debug_output_dir.strip("/\\") or "ocr"
        path = target_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def language_priority(self) -> tuple[str, ...]:
        extra = tuple(s.strip() for s in self.ocr_extra_languages.split(",") if s.strip())
        from kuvien_parsinta.languages import merge_language_priority

        return merge_language_priority(primary=self.ocr_primary_language, extra=extra)

    def resolved_ocr_device(self) -> str:
        device = resolve_paddle_device(self.ocr_device)
        if device.startswith("gpu"):
            configure_cuda_runtime()
        return device

    def resolved_vl_device(self) -> str:
        device = resolve_paddle_device(self.vl_device)
        if device.startswith("gpu"):
            configure_cuda_runtime()
        return device


@lru_cache
def get_settings() -> Settings:
    return Settings()
