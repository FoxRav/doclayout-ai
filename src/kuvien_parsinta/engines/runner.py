"""Orchestrate hybrid, VL-only, StructureV3-only, and best-mode parsing."""

from __future__ import annotations

from pathlib import Path

import structlog

from kuvien_parsinta.config import Settings
from kuvien_parsinta.engines.artifacts import alias_structure_json
from kuvien_parsinta.engines.compare import write_compare_report
from kuvien_parsinta.engines.hybrid import merge_hybrid_outputs
from kuvien_parsinta.engines.paddleocr_vl_engine import VlEngineOutput, VlNotInstalledError, run_paddleocr_vl
from kuvien_parsinta.engines.structurev3_engine import StructureV3Output, run_structurev3
from kuvien_parsinta.engines.types import EngineRunOutput
from kuvien_parsinta.fallback import ParseEngine
from kuvien_parsinta.models import OutputMode, ParseEngineChoice

logger = structlog.get_logger(__name__)


class EngineRunError(RuntimeError):
    """Engine pipeline failed without a usable result."""

    def __init__(self, message: str, *, engines_tried: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.engines_tried = engines_tried


def resolve_engine_choice(
    *,
    cli_engine: ParseEngineChoice | None,
    settings_engine: ParseEngineChoice,
    speed_priority: bool = False,
) -> ParseEngineChoice:
    if cli_engine is not None:
        return cli_engine
    if settings_engine is ParseEngineChoice.AUTO:
        return ParseEngineChoice.STRUCTUREV3 if speed_priority else ParseEngineChoice.HYBRID
    return settings_engine


def run_parse_engines(
    *,
    source: Path,
    target_dir: Path,
    settings: Settings,
    output_mode: OutputMode,
    engine_choice: ParseEngineChoice,
) -> EngineRunOutput:
    """Run selected engine strategy and return unified output."""
    priority = settings.language_priority()
    device = settings.resolved_ocr_device()
    vl_device = settings.resolved_vl_device()

    match engine_choice:
        case ParseEngineChoice.HYBRID | ParseEngineChoice.AUTO:
            return _run_hybrid(
                source=source,
                target_dir=target_dir,
                settings=settings,
                output_mode=output_mode,
                priority=priority,
                device=device,
                vl_device=vl_device,
                save_comparison=False,
            )
        case ParseEngineChoice.BEST:
            return _run_hybrid(
                source=source,
                target_dir=target_dir,
                settings=settings,
                output_mode=output_mode,
                priority=priority,
                device=device,
                vl_device=vl_device,
                save_comparison=True,
            )
        case ParseEngineChoice.VL:
            return _run_vl_only(
                source=source,
                target_dir=target_dir,
                settings=settings,
                output_mode=output_mode,
                priority=priority,
                device=device,
                vl_device=vl_device,
            )
        case ParseEngineChoice.STRUCTUREV3:
            return _run_structure_only(
                source=source,
                target_dir=target_dir,
                settings=settings,
                output_mode=output_mode,
                priority=priority,
                device=device,
            )
        case _:
            raise ValueError(f"Unsupported engine choice: {engine_choice}")


def _run_hybrid(
    *,
    source: Path,
    target_dir: Path,
    settings: Settings,
    output_mode: OutputMode,
    priority: tuple[str, ...],
    device: str,
    vl_device: str,
    save_comparison: bool,
) -> EngineRunOutput:
    """Run VL + StructureV3 and merge into hybrid output."""
    engines_run: list[str] = []
    debug_paths: list[Path] = []
    structure_out: StructureV3Output | None = None
    vl_out: VlEngineOutput | None = None
    structure_alias: Path | None = None
    primary = ParseEngine.HYBRID.value
    fallback_used = False
    fallback_reason: str | None = None
    fallback_engine: str | None = None

    if settings.structurev3_enabled:
        structure_out = _try_structure(
            source=source,
            target_dir=target_dir,
            settings=settings,
            output_mode=output_mode,
            priority=priority,
            device=device,
            log_prefix="hybrid_structurev3",
        )
        if structure_out is not None:
            engines_run.append(ParseEngine.PP_STRUCTURE.value)
            structure_alias = alias_structure_json(
                source=structure_out.structure_json_path,
                work_dir=target_dir / "ocr",
                stem=source.stem,
            )
            debug_paths.extend((structure_out.structure_json_path, structure_alias))

    if settings.vl_enabled:
        vl_out = _try_vl(
            source=source,
            target_dir=target_dir,
            settings=settings,
            output_mode=output_mode,
            vl_device=vl_device,
        )
        if vl_out is not None:
            engines_run.append(ParseEngine.PADDLE_VL.value)
            debug_paths.extend((vl_out.vl_json_path, vl_out.vl_markdown_path))

    if structure_out is None and vl_out is None:
        raise EngineRunError(
            "hybrid mode: both StructureV3 and PaddleOCR-VL failed",
            engines_tried=tuple(engines_run),
        )

    if vl_out is None:
        fallback_used = True
        fallback_engine = ParseEngine.PP_STRUCTURE.value
        fallback_reason = "PaddleOCR-VL unavailable; hybrid uses StructureV3 only"
        if settings.no_silent_fallback:
            logger.warning(
                "hybrid_degraded",
                primary_engine=primary,
                fallback_engine=fallback_engine,
                reason=fallback_reason,
            )
    elif structure_out is None:
        fallback_used = True
        fallback_engine = ParseEngine.PADDLE_VL.value
        fallback_reason = "StructureV3 unavailable; hybrid uses VL only (layout degraded)"
        if settings.no_silent_fallback:
            logger.warning(
                "hybrid_degraded",
                primary_engine=primary,
                fallback_engine=fallback_engine,
                reason=fallback_reason,
            )

    merged = merge_hybrid_outputs(
        source_stem=source.stem,
        target_dir=target_dir,
        vl_out=vl_out,
        structure_out=structure_out,
        settings=settings,
        output_mode=output_mode,
    )
    debug_paths.append(merged.hybrid_json_path)

    compare_path: Path | None = None
    if save_comparison or settings.save_engine_comparison:
        compare_path = write_compare_report(
            target_dir=target_dir,
            stem=source.stem,
            structure_out=structure_out,
            vl_out=vl_out,
            selected_engine=ParseEngine.HYBRID,
            primary_engine=ParseEngine.HYBRID,
            conflicts=merged.conflicts,
            hybrid_json_path=merged.hybrid_json_path,
        )
        debug_paths.append(compare_path)

    languages = structure_out.languages_tried if structure_out is not None else ()
    page_count = max(
        vl_out.page_count if vl_out else 0,
        structure_out.page_count if structure_out else 0,
        1,
    )

    return EngineRunOutput(
        engine=ParseEngine.HYBRID,
        markdown_text=merged.markdown_text,
        confidence_avg=merged.confidence_avg,
        page_count=page_count,
        uses_layout_pdf=merged.uses_layout_pdf,
        primary_engine=primary,
        fallback_engine=fallback_engine,
        languages_tried=languages,
        structure_json_path=structure_out.structure_json_path if structure_out else None,
        structurev3_json_path=structure_alias,
        vl_json_path=vl_out.vl_json_path if vl_out else None,
        vl_markdown_path=vl_out.vl_markdown_path if vl_out else None,
        document=merged.pdf_document,
        layout_helper_document=structure_out.document if structure_out else None,
        debug_paths=tuple(dict.fromkeys(debug_paths)),
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        engines_run=tuple(engines_run),
        compare_report_path=compare_path,
        hybrid_json_path=merged.hybrid_json_path,
        layout_helper_engine=(
            ParseEngine.PP_STRUCTURE.value if structure_out is not None else None
        ),
        text_source=merged.text_source,
        layout_source=merged.layout_source,
    )


def _run_structure_only(
    *,
    source: Path,
    target_dir: Path,
    settings: Settings,
    output_mode: OutputMode,
    priority: tuple[str, ...],
    device: str,
) -> EngineRunOutput:
    """Run PP-StructureV3 only — regression / comparison mode."""
    if not settings.structurev3_enabled:
        raise EngineRunError(
            "StructureV3 is disabled (PARSE_STRUCTUREV3_ENABLED=false)",
            engines_tried=(ParseEngine.PP_STRUCTURE.value,),
        )
    structure = run_structurev3(
        source=source,
        target_dir=target_dir,
        priority=priority,
        device=device,
        output_mode=output_mode,
        confidence_threshold=settings.ocr_vl_confidence_threshold,
        quality=settings.quality,
    )
    return EngineRunOutput(
        engine=ParseEngine.PP_STRUCTURE,
        markdown_text=structure.markdown_text,
        confidence_avg=structure.confidence_avg,
        page_count=structure.page_count,
        uses_layout_pdf=structure.uses_layout_pdf,
        primary_engine=ParseEngine.PP_STRUCTURE.value,
        languages_tried=structure.languages_tried,
        structure_json_path=structure.structure_json_path,
        document=structure.document,
        debug_paths=(structure.structure_json_path,),
        engines_run=(ParseEngine.PP_STRUCTURE.value,),
        text_source=ParseEngine.PP_STRUCTURE.value,
        layout_source=ParseEngine.PP_STRUCTURE.value,
    )


def _run_vl_only(
    *,
    source: Path,
    target_dir: Path,
    settings: Settings,
    output_mode: OutputMode,
    priority: tuple[str, ...],
    device: str,
    vl_device: str,
) -> EngineRunOutput:
    """Run PaddleOCR-VL only — testing / comparison mode."""
    primary = ParseEngine.PADDLE_VL.value
    engines_run: list[str] = [primary]

    if not settings.vl_enabled:
        raise EngineRunError(
            "PaddleOCR-VL is disabled (PARSE_VL_ENABLED=false)",
            engines_tried=(primary,),
        )

    try:
        vl_out = run_paddleocr_vl(
            input_path=source,
            target_dir=target_dir,
            pipeline_version=settings.vl_pipeline_version,
            device=vl_device,
            save_raw=settings.vl_save_raw,
            output_mode=output_mode,
            quality=settings.quality,
        )
    except (RuntimeError, OSError, VlNotInstalledError) as exc:
        logger.error("paddleocr_vl_failed", error=str(exc))
        if not settings.vl_fallback_on_error or not settings.structurev3_enabled:
            raise EngineRunError(
                f"PaddleOCR-VL failed: {exc}",
                engines_tried=(primary,),
            ) from exc

        logger.warning(
            "paddleocr_vl_fallback_to_structurev3",
            primary_engine=primary,
            fallback_engine=ParseEngine.PP_STRUCTURE.value,
            reason=str(exc),
        )
        structure = _run_structure_or_raise(
            source=source,
            target_dir=target_dir,
            settings=settings,
            output_mode=output_mode,
            priority=priority,
            device=device,
            engines_tried=(primary, ParseEngine.PP_STRUCTURE.value),
            vl_error=exc,
        )
        engines_run.append(ParseEngine.PP_STRUCTURE.value)
        return EngineRunOutput(
            engine=ParseEngine.PP_STRUCTURE,
            markdown_text=structure.markdown_text,
            confidence_avg=structure.confidence_avg,
            page_count=structure.page_count,
            uses_layout_pdf=structure.uses_layout_pdf,
            primary_engine=primary,
            fallback_engine=ParseEngine.PP_STRUCTURE.value,
            languages_tried=structure.languages_tried,
            structure_json_path=structure.structure_json_path,
            document=structure.document,
            debug_paths=(structure.structure_json_path,),
            fallback_used=True,
            fallback_reason=f"PaddleOCR-VL error: {exc}",
            engines_run=tuple(engines_run),
            text_source=ParseEngine.PP_STRUCTURE.value,
            layout_source=ParseEngine.PP_STRUCTURE.value,
        )

    return EngineRunOutput(
        engine=ParseEngine.PADDLE_VL,
        markdown_text=vl_out.markdown_text,
        confidence_avg=vl_out.confidence_avg,
        page_count=vl_out.page_count,
        uses_layout_pdf=vl_out.uses_layout_pdf,
        primary_engine=primary,
        vl_json_path=vl_out.vl_json_path,
        vl_markdown_path=vl_out.vl_markdown_path,
        document=vl_out.document,
        debug_paths=(vl_out.vl_json_path, vl_out.vl_markdown_path),
        engines_run=tuple(engines_run),
        text_source=ParseEngine.PADDLE_VL.value,
        layout_source=ParseEngine.PADDLE_VL.value,
    )


def _try_structure(
    *,
    source: Path,
    target_dir: Path,
    settings: Settings,
    output_mode: OutputMode,
    priority: tuple[str, ...],
    device: str,
    log_prefix: str,
) -> StructureV3Output | None:
    try:
        return run_structurev3(
            source=source,
            target_dir=target_dir,
            priority=priority,
            device=device,
            output_mode=output_mode,
            confidence_threshold=settings.ocr_vl_confidence_threshold,
            quality=settings.quality,
        )
    except (RuntimeError, OSError, ImportError) as exc:
        logger.warning(f"{log_prefix}_failed", error=str(exc))
        return None


def _run_structure_or_raise(
    *,
    source: Path,
    target_dir: Path,
    settings: Settings,
    output_mode: OutputMode,
    priority: tuple[str, ...],
    device: str,
    engines_tried: tuple[str, ...],
    vl_error: Exception,
) -> StructureV3Output:
    try:
        return run_structurev3(
            source=source,
            target_dir=target_dir,
            priority=priority,
            device=device,
            output_mode=output_mode,
            confidence_threshold=settings.ocr_vl_confidence_threshold,
            quality=settings.quality,
        )
    except (RuntimeError, OSError, ImportError) as struct_exc:
        raise EngineRunError(
            f"PaddleOCR-VL failed ({vl_error}) and StructureV3 fallback failed ({struct_exc})",
            engines_tried=engines_tried,
        ) from struct_exc


def _try_vl(
    *,
    source: Path,
    target_dir: Path,
    settings: Settings,
    output_mode: OutputMode,
    vl_device: str,
) -> VlEngineOutput | None:
    if not settings.vl_enabled:
        return None
    try:
        return run_paddleocr_vl(
            input_path=source,
            target_dir=target_dir,
            pipeline_version=settings.vl_pipeline_version,
            device=vl_device,
            save_raw=settings.vl_save_raw,
            output_mode=output_mode,
            quality=settings.quality,
        )
    except (RuntimeError, OSError, VlNotInstalledError) as exc:
        logger.error("paddleocr_vl_unavailable", error=str(exc))
        return None
