"""Parse pipeline orchestrator."""

from __future__ import annotations

from pathlib import Path

import structlog

from kuvien_parsinta.config import Settings, get_settings
from kuvien_parsinta.engines.compare import merge_layout_into_compare_report, merge_search_text_into_compare_report
from kuvien_parsinta.engines.runner import EngineRunError, resolve_engine_choice, run_parse_engines
from kuvien_parsinta.layout.newspaper_page_model import (
    NewspaperPageModel,
    build_newspaper_page_model,
    save_page_model_debug,
)
from kuvien_parsinta.layout.page_layout import DocumentType
from kuvien_parsinta.layout.page_layout_builder import (
    build_page_layout,
    layout_quality_metrics,
    save_layout_debug_image,
)
from kuvien_parsinta.models import InputKind, OutputMode, ParseEngineChoice, ParseResult, PdfMode, QualityMode
from kuvien_parsinta.output.primary_outputs import write_primary_outputs
from kuvien_parsinta.output_paths import resolve_output_dir
from kuvien_parsinta.pdf.facsimile_pdf import raster_similarity_to_source, render_facsimile_pdf
from kuvien_parsinta.pdf.search_text_layer import build_search_text_layer
from kuvien_parsinta.pdf.newspaper_template_renderer import (
    render_newspaper_template_pdf,
    save_template_render_report,
)
from kuvien_parsinta.pdf.structural_newspaper_pdf import render_structural_newspaper_pdf
from kuvien_parsinta.quality.newspaper_quality_gate import (
    append_error_log,
    run_newspaper_quality_gate,
    save_quality_report,
)
from kuvien_parsinta.pdf.layout_pdf import (
    render_clean_pdf,
    render_ocr_overlay_debug_pdf,
    render_search_layer_debug_pdf,
)
from kuvien_parsinta.pdf.output_policy import resolve_pdf_output_plan
from kuvien_parsinta.router import detect_input_kind

logger = structlog.get_logger(__name__)


class ParsePipeline:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def parse(
        self,
        source: Path,
        *,
        out_dir: Path | None = None,
        mode: OutputMode | None = None,
        engine: ParseEngineChoice | None = None,
        quality: QualityMode | None = None,
        pdf_mode: PdfMode | None = None,
        emit_facsimile: bool | None = None,
        emit_clean: bool | None = None,
        debug_pdf: bool | None = None,
    ) -> ParseResult:
        source = source.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Input not found: {source}")

        kind = detect_input_kind(source)
        if kind is InputKind.UNKNOWN:
            raise ValueError(f"Unsupported file type: {source.suffix}")

        output_mode = mode or self._settings.default_output_mode
        target_dir = resolve_output_dir(source, out_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        effective_quality = quality or self._settings.quality
        effective_pdf_mode = pdf_mode or self._settings.pdf_mode
        settings = self._settings.model_copy(
            update={
                "quality": effective_quality,
                "pdf_mode": effective_pdf_mode,
                "emit_facsimile": (
                    emit_facsimile if emit_facsimile is not None else self._settings.emit_facsimile
                ),
                "emit_clean": emit_clean if emit_clean is not None else self._settings.emit_clean,
                "emit_debug_pdf": (
                    debug_pdf if debug_pdf is not None else self._settings.emit_debug_pdf
                ),
            }
        )

        engine_choice = resolve_engine_choice(
            cli_engine=engine,
            settings_engine=settings.engine,
            speed_priority=settings.speed_priority,
        )
        logger.info(
            "parse_start",
            source=str(source),
            engine_requested=engine_choice.value,
            output_mode=output_mode.value,
            quality=effective_quality.value,
            pdf_mode=effective_pdf_mode.value,
        )

        result, engine_markdown = self._parse_with_engines(
            source=source,
            target_dir=target_dir,
            output_mode=output_mode,
            engine_choice=engine_choice,
            settings=settings,
            quality=effective_quality,
        )

        ocr_dir = settings.debug_dir(target_dir)
        structure_json = ocr_dir / f"{source.stem}_structurev3_res.json"
        if not structure_json.is_file():
            structure_json = ocr_dir / f"{source.stem}_res.json"
        vl_json = ocr_dir / f"{source.stem}_vl_res.json"

        layout = None
        newspaper_model: NewspaperPageModel | None = None
        if kind is InputKind.IMAGE:
            layout = build_page_layout(
                source_path=source,
                structure_json_path=structure_json if structure_json.is_file() else None,
                vl_json_path=vl_json if vl_json.is_file() else None,
            )
            if layout is not None and layout.document_type is DocumentType.NEWSPAPER_FRONT_PAGE:
                tmp_dir = settings.debug_dir(target_dir) / ".tmp_crops"
                newspaper_model = build_newspaper_page_model(
                    layout=layout,
                    source_path=source,
                    vl_json_path=vl_json if vl_json.is_file() else None,
                    structure_json_path=structure_json if structure_json.is_file() else None,
                    tmp_dir=tmp_dir,
                )
                from kuvien_parsinta.text.newspaper_content_assembly import (
                    assemble_newspaper_page_model_content,
                )

                newspaper_model = assemble_newspaper_page_model_content(
                    newspaper_model,
                    vl_json_path=vl_json if vl_json.is_file() else None,
                    structure_json_path=structure_json if structure_json.is_file() else None,
                    page_width_px=layout.page_width_px,
                    page_height_px=layout.page_height_px,
                )
                from kuvien_parsinta.text.final_text_cleanup import apply_cleanup_to_page_model

                newspaper_model = apply_cleanup_to_page_model(newspaper_model)
                save_page_model_debug(
                    model=newspaper_model,
                    output_path=ocr_dir / f"{source.stem}_page_model.json",
                )

        primary_outputs = write_primary_outputs(
            source=source,
            target_dir=target_dir,
            engine_markdown=engine_markdown,
            result=result,
            settings=settings,
            kind=kind,
            layout=layout,
            vl_json=vl_json if vl_json.is_file() else None,
            pdf_render_fn=self._render_layout_pdfs,
            newspaper_model=newspaper_model,
        )

        quality_passed: bool | None = None
        quality_status: str | None = None
        quality_report_path: Path | None = None
        if layout is not None and layout.document_type is DocumentType.NEWSPAPER_FRONT_PAGE:
            ocr_dir = settings.debug_dir(target_dir)
            content_audit_path = ocr_dir / f"{source.stem}_content_audit.json"
            gate_result = run_newspaper_quality_gate(
                stem=source.stem,
                target_dir=target_dir,
                ocr_dir=ocr_dir,
                markdown_path=primary_outputs.markdown_path,
                structural_pdf_path=primary_outputs.structural_pdf_path,
                pdf_width_pt=layout.pdf_width_pt,
                pdf_height_pt=layout.pdf_height_pt,
                emit_facsimile=settings.emit_facsimile,
                page_model=newspaper_model,
                style_debug_path=ocr_dir / f"{source.stem}_style_debug.json",
                visual_metrics_path=ocr_dir / f"{source.stem}_visual_metrics.json",
                content_audit_path=content_audit_path,
            )
            quality_report_path = save_quality_report(
                result=gate_result,
                output_path=ocr_dir / f"{source.stem}_quality_report.json",
            )
            quality_passed = gate_result.passed
            quality_status = gate_result.status
            if not gate_result.passed:
                error_log = ocr_dir / f"{source.stem}_error_log.jsonl"
                for check in gate_result.checks:
                    if not check.passed:
                        append_error_log(
                            output_path=error_log,
                            error_id="QUALITY-GATE",
                            message=f"{check.name}: {check.detail}".strip(": "),
                        )
                logger.warning("quality_gate_failed", failed_checks=[c.name for c in gate_result.checks if not c.passed])

        return result.model_copy(
            update={
                "markdown_path": primary_outputs.markdown_path,
                "pdf_path": primary_outputs.pdf_path,
                "structural_pdf_path": primary_outputs.structural_pdf_path,
                "facsimile_pdf_path": primary_outputs.facsimile_pdf_path,
                "clean_pdf_path": primary_outputs.clean_pdf_path,
                "layout_debug_path": primary_outputs.layout_debug_path,
                "structural_debug_path": primary_outputs.structural_debug_path,
                "structural_report_path": primary_outputs.structural_report_path,
                "search_text_path": primary_outputs.search_text_path,
                "ocr_overlay_debug_path": primary_outputs.structural_debug_path,
                "quality_passed": quality_passed,
                "quality_status": quality_status if layout is not None and layout.document_type is DocumentType.NEWSPAPER_FRONT_PAGE else None,
                "quality_report_path": quality_report_path,
            }
        )

    def _parse_with_engines(
        self,
        *,
        source: Path,
        target_dir: Path,
        output_mode: OutputMode,
        engine_choice: ParseEngineChoice,
        settings: Settings,
        quality: QualityMode,
    ) -> tuple[ParseResult, str]:
        try:
            output = run_parse_engines(
                source=source,
                target_dir=target_dir,
                settings=settings,
                output_mode=output_mode,
                engine_choice=engine_choice,
            )
        except EngineRunError:
            raise
        except ImportError as exc:
            raise ImportError(
                "OCR stack not installed. Run scripts\\setup.ps1 "
                "and optionally scripts\\install_paddleocr_vl.ps1"
            ) from exc

        if not output.markdown_text.strip():
            raise RuntimeError("primary markdown output was not written")

        if output.fallback_used:
            logger.warning(
                "engine_fallback",
                primary_engine=output.primary_engine,
                fallback_engine=output.fallback_engine,
                reason=output.fallback_reason,
                selected=output.engine.value,
                engines_run=list(output.engines_run),
            )

        raw_json = output.hybrid_json_path or output.vl_json_path or output.structure_json_path
        md_path = target_dir / f"{source.stem}.md"

        parse_result = ParseResult(
            source=source,
            markdown_path=md_path,
            engine_used=str(output.engine.value),
            primary_engine=output.primary_engine or output.engine.value,
            fallback_engine=output.fallback_engine,
            languages_tried=output.languages_tried,
            ocr_confidence_avg=output.confidence_avg,
            page_count=output.page_count,
            uses_layout_pdf=output.uses_layout_pdf,
            engine_requested=engine_choice.value,
            engines_run=output.engines_run,
            fallback_used=output.fallback_used,
            fallback_reason=output.fallback_reason,
            debug_artifacts=output.debug_paths,
            vl_markdown_path=output.vl_markdown_path,
            raw_json_path=raw_json,
            compare_report_path=output.compare_report_path,
            hybrid_json_path=output.hybrid_json_path,
            layout_document=output.document,
            text_source=output.text_source,
            layout_source=output.layout_source,
            quality_mode=quality.value,
            layout_helper_engine=output.layout_helper_engine,
        )
        return parse_result, output.markdown_text

    def _render_layout_pdfs(
        self,
        *,
        source: Path,
        md_path: Path,
        target_dir: Path,
        result: ParseResult,
        settings: Settings,
        layout: object | None = None,
        vl_json: Path | None = None,
        newspaper_model: NewspaperPageModel | None = None,
    ) -> dict[str, Path | None]:
        from kuvien_parsinta.layout.page_layout import PageLayout

        ocr_dir = settings.debug_dir(target_dir)
        structure_json = ocr_dir / f"{source.stem}_structurev3_res.json"
        if not structure_json.is_file():
            structure_json = ocr_dir / f"{source.stem}_res.json"
        if layout is None or not isinstance(layout, PageLayout):
            vl_json_path = vl_json if vl_json is not None else ocr_dir / f"{source.stem}_vl_res.json"
            layout = build_page_layout(
                source_path=source,
                structure_json_path=structure_json if structure_json.is_file() else None,
                vl_json_path=vl_json_path if vl_json_path.is_file() else None,
            )
        vl_json_path = vl_json if vl_json is not None else ocr_dir / f"{source.stem}_vl_res.json"

        layout_debug_path: Path | None = None
        structural_debug_path: Path | None = None
        structural_report_path: Path | None = None
        search_text_layer = None
        search_text_path: Path | None = None
        if layout is not None:
            debug_path = ocr_dir / f"{source.stem}_layout_debug.jpg"
            save_layout_debug_image(source_path=source, layout=layout, output_path=debug_path)
            layout_debug_path = debug_path
            search_text_layer = build_search_text_layer(
                layout=layout,
                vl_json_path=vl_json_path if vl_json_path.is_file() else None,
            )
            logger.info(
                "page_layout_built",
                document_type=layout.document_type.value,
                blocks=len(layout.blocks),
                search_text_segments=search_text_layer.block_count_after,
                dedup_removed=len(search_text_layer.removed_duplicates),
            )

        use_fixed_layout = (
            layout is not None
            and settings.layout_preserve
            and (
                layout.document_type is DocumentType.NEWSPAPER_FRONT_PAGE
                or result.uses_layout_pdf
            )
        )

        output_plan = resolve_pdf_output_plan(
            pdf_mode=settings.pdf_mode.value,
            emit_facsimile=settings.emit_facsimile,
            emit_clean=settings.emit_clean,
            emit_debug_pdf=settings.emit_debug_pdf,
        )

        reflow_used = False
        structural_path: Path | None = None
        facsimile_path: Path | None = None
        clean_path: Path | None = None
        raster_similarity: float | None = None
        tmp_dir = ocr_dir / ".tmp_crops"
        structural_report = None

        if layout is not None and output_plan.debug_overlay:
            overlay_path = ocr_dir / f"{source.stem}_ocr_overlay_debug.pdf"
            try:
                render_ocr_overlay_debug_pdf(
                    source_path=source,
                    layout=layout,
                    pdf_path=overlay_path,
                    draw_bbox=True,
                )
                structural_debug_path = overlay_path
            except (FileNotFoundError, ValueError, OSError) as exc:
                logger.warning("structural_debug_failed", error=str(exc))

        if layout is not None and output_plan.debug_search_layer and search_text_layer is not None:
            search_debug_path = ocr_dir / f"{source.stem}_search_layer_debug.pdf"
            try:
                render_search_layer_debug_pdf(
                    search_text=search_text_layer.full_text,
                    layout=layout,
                    pdf_path=search_debug_path,
                )
                search_text_path = search_debug_path
            except (FileNotFoundError, ValueError, OSError) as exc:
                logger.warning("search_layer_debug_failed", error=str(exc))

        if settings.facsimile_draw_debug or settings.facsimile_draw_bbox:
            logger.warning(
                "facsimile_debug_flags_ignored",
                message="Use --debug-pdf for ocr/*_ocr_overlay_debug.pdf",
            )

        if output_plan.structural and layout is not None and use_fixed_layout:
            out_path = target_dir / f"{source.stem}_structural.pdf"
            try:
                if layout.document_type is DocumentType.NEWSPAPER_FRONT_PAGE:
                    if newspaper_model is None:
                        newspaper_model = build_newspaper_page_model(
                            layout=layout,
                            source_path=source,
                            vl_json_path=vl_json_path if vl_json_path.is_file() else None,
                            structure_json_path=structure_json if structure_json.is_file() else None,
                            tmp_dir=tmp_dir,
                        )
                    _, structural_report, _typography_plan = render_newspaper_template_pdf(
                        model=newspaper_model,
                        layout=layout,
                        pdf_path=out_path,
                        source_path=source,
                        settings=settings,
                        tmp_dir=tmp_dir,
                        style_debug_path=ocr_dir / f"{source.stem}_style_debug.json",
                        visual_metrics_path=ocr_dir / f"{source.stem}_visual_metrics.json",
                        source_alignment_path=ocr_dir / f"{source.stem}_source_alignment_metrics.json",
                    )
                else:
                    _, structural_report = render_structural_newspaper_pdf(
                        source_path=source,
                        layout=layout,
                        pdf_path=out_path,
                        vl_json_path=vl_json_path if vl_json_path.is_file() else None,
                        tmp_dir=tmp_dir,
                    )
                structural_path = out_path
                structural_report_path = save_template_render_report(
                    report=structural_report,
                    output_path=ocr_dir / f"{source.stem}_structural_report.json",
                )
            except (FileNotFoundError, ValueError, OSError) as exc:
                logger.warning("structural_pdf_failed", error=str(exc))

        if output_plan.facsimile and layout is not None and use_fixed_layout:
            facsimile_out = ocr_dir / f"{source.stem}_facsimile.pdf"
            try:
                render_facsimile_pdf(
                    source_path=source,
                    layout=layout,
                    pdf_path=facsimile_out,
                    search_text=(
                        search_text_layer.full_text if search_text_layer is not None else None
                    ),
                    invisible_text=settings.facsimile_invisible_text,
                    visible_ocr=settings.facsimile_visible_ocr,
                )
                facsimile_path = facsimile_out
                try:
                    raster_similarity = raster_similarity_to_source(source, facsimile_out)
                except (FileNotFoundError, ValueError, OSError) as exc:
                    logger.warning("facsimile_raster_check_failed", error=str(exc))
            except (FileNotFoundError, ValueError, OSError) as exc:
                logger.warning("facsimile_pdf_failed", error=str(exc))

        if output_plan.clean:
            clean_out = target_dir / f"{source.stem}_clean.pdf"
            try:
                render_clean_pdf(md_path=md_path, pdf_path=clean_out)
                clean_path = clean_out
                reflow_used = True
            except (FileNotFoundError, ValueError, OSError) as exc:
                logger.warning("clean_pdf_failed", error=str(exc))

        if layout is not None and result.compare_report_path is not None:
            metrics = layout_quality_metrics(
                layout=layout,
                pdf_mode=settings.pdf_mode.value,
                layout_preserve=settings.layout_preserve,
                reflow_used=reflow_used and not use_fixed_layout,
                visible_text_overlay=settings.facsimile_visible_ocr,
                debug_boxes_visible=settings.facsimile_draw_bbox or settings.facsimile_draw_debug,
                visible_ocr=settings.facsimile_visible_ocr,
                raster_similarity_to_source=raster_similarity,
            )
            merge_layout_into_compare_report(
                result.compare_report_path,
                metrics.to_compare_fields(),
            )
            if search_text_layer is not None:
                merge_search_text_into_compare_report(
                    result.compare_report_path,
                    search_text_layer.to_compare_fields(),
                )
            if structural_report is not None:
                merge_search_text_into_compare_report(
                    result.compare_report_path,
                    structural_report.to_json_dict(),
                )

        primary = structural_path or clean_path
        if primary is None and not settings.reflow_text and layout is not None:
            logger.warning("structural_pdf_missing", fallback="none")

        return {
            "pdf_path": primary,
            "structural_pdf_path": structural_path,
            "facsimile_pdf_path": facsimile_path,
            "rebuild_pdf_path": None,
            "clean_pdf_path": clean_path,
            "layout_debug_path": layout_debug_path,
            "structural_debug_path": structural_debug_path,
            "structural_report_path": structural_report_path,
            "search_text_path": search_text_path,
            "ocr_overlay_debug_path": structural_debug_path,
        }
