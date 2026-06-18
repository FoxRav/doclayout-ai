"""CLI entry point."""

from __future__ import annotations

from pathlib import Path

import typer
from rich import print as rprint

from kuvien_parsinta.engines.runner import EngineRunError
from kuvien_parsinta.models import OutputMode, ParseEngineChoice, PdfMode, QualityMode
from kuvien_parsinta.pipeline import ParsePipeline

app = typer.Typer(help="doclayout-ai: multilingual image/PDF → markdown + PDF")


@app.command()
def parse(
    input_path: Path = typer.Argument(..., help="Image or PDF file"),
    out_dir: Path | None = typer.Option(
        None, "--out-dir", "-o", help="Override output directory (default: input file folder)"
    ),
    mode: OutputMode = typer.Option(OutputMode.AUTO, "--mode", "-m", help="Output markdown style"),
    engine: ParseEngineChoice | None = typer.Option(
        None,
        "--engine",
        "-e",
        help="Parse engine: hybrid (default), vl, structurev3, or best",
    ),
    quality: QualityMode | None = typer.Option(
        None,
        "--quality",
        "-q",
        help="Quality mode: standard or max (default from PARSE_QUALITY)",
    ),
    pdf_mode: PdfMode | None = typer.Option(
        None,
        "--pdf-mode",
        help="Primary PDF type: structural (default), clean, or facsimile",
    ),
    emit_facsimile: bool = typer.Option(
        False,
        "--emit-facsimile",
        help="Also write ocr/<name>_facsimile.pdf (archive copy)",
    ),
    emit_clean: bool = typer.Option(
        False,
        "--emit-clean",
        help="Also write <name>_clean.pdf (reflowed text PDF)",
    ),
    debug_pdf: bool = typer.Option(
        False,
        "--debug-pdf",
        help="Write debug PDFs under ocr/ (overlay + search layer)",
    ),
    no_pdf: bool = typer.Option(False, "--no-pdf", help="Skip PDF generation"),
) -> None:
    """Parse one file to markdown (and structural PDF by default)."""
    from kuvien_parsinta.config import get_settings

    settings = get_settings()
    if no_pdf:
        settings = settings.model_copy(update={"write_pdf": False})
    else:
        settings = settings.model_copy(
            update={
                "emit_facsimile": emit_facsimile,
                "emit_clean": emit_clean,
                "emit_debug_pdf": debug_pdf,
            }
        )

    pipeline = ParsePipeline(settings)
    try:
        result = pipeline.parse(
            input_path,
            out_dir=out_dir,
            mode=mode,
            engine=engine,
            quality=quality,
            pdf_mode=pdf_mode,
            emit_facsimile=emit_facsimile,
            emit_clean=emit_clean,
            debug_pdf=debug_pdf,
        )
    except EngineRunError as exc:
        rprint(f"[red]Parse failed:[/red] {exc}")
        if exc.engines_tried:
            rprint(f"Engines tried: {', '.join(exc.engines_tried)}")
        raise typer.Exit(code=1) from exc
    except (FileNotFoundError, ValueError) as exc:
        rprint(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except ImportError as exc:
        rprint(
            "[red]OCR stack not installed.[/red] Run:\n"
            "  powershell -ExecutionPolicy Bypass -File scripts\\setup.ps1"
        )
        raise typer.Exit(code=1) from exc

    _print_run_summary(result, settings)


def _print_run_summary(result: object, settings: object) -> None:
    from kuvien_parsinta.config import Settings
    from kuvien_parsinta.models import ParseResult

    if not isinstance(result, ParseResult) or not isinstance(settings, Settings):
        return

    rprint("[bold]Tuotetut päätiedostot:[/bold]")
    if result.markdown_path and result.markdown_path.is_file():
        rprint(f"  {result.markdown_path}")
    if result.structural_pdf_path and result.structural_pdf_path.is_file():
        rprint(f"  {result.structural_pdf_path}")

    debug_paths = [
        path
        for path in (
            result.layout_debug_path,
            result.structural_report_path,
            result.compare_report_path,
            result.hybrid_json_path,
            result.structural_debug_path,
            result.search_text_path,
            result.facsimile_pdf_path,
        )
        if path is not None and path.is_file()
    ]
    if debug_paths:
        rprint("[bold]Debug:[/bold]")
        for path in debug_paths:
            rprint(f"  {path}")

    rprint(f"[dim]Primary engine:[/dim] {result.primary_engine}")
    rprint(f"Selected engine: {result.engine_used} | device: {settings.resolved_vl_device()}")
    if result.text_source:
        rprint(f"Text source: {result.text_source}")
    if result.layout_source:
        rprint(f"Layout source: {result.layout_source}")
    if result.engine_requested:
        rprint(f"Requested: {result.engine_requested}")
    if result.quality_mode:
        rprint(f"Quality: {result.quality_mode}")
    if result.engines_run:
        rprint(f"Engines run: {', '.join(result.engines_run)}")
    if result.fallback_used:
        rprint(
            f"[yellow]Fallback:[/yellow] {result.primary_engine} → "
            f"{result.fallback_engine} ({result.fallback_reason})"
        )
    else:
        rprint("Fallback: no")
    if result.layout_helper_engine:
        rprint(f"Layout helper: {result.layout_helper_engine}")
    rprint(f"Langs: {', '.join(result.languages_tried) or '-'}")
    if result.ocr_confidence_avg is not None:
        rprint(f"OCR confidence: {result.ocr_confidence_avg:.3f}")
    if result.quality_passed is not None:
        status_label = getattr(result, "quality_status", None) or "pass"
        if not result.quality_passed:
            rprint("[red]QUALITY: FAIL[/red]")
        elif status_label == "pass_with_warnings":
            rprint("[yellow]QUALITY: PASS_WITH_WARNINGS[/yellow]")
        else:
            rprint("[green]QUALITY: PASS[/green]")
        if result.quality_report_path and result.quality_report_path.is_file():
            rprint(f"[dim]Quality report:[/dim] {result.quality_report_path}")


@app.command()
def languages() -> None:
    """Show configured OCR language priority."""
    from kuvien_parsinta.config import get_settings

    s = get_settings()
    rprint("Primary:", s.ocr_primary_language)
    rprint("Priority:", ", ".join(s.language_priority()))
    rprint("Mode:", s.ocr_language_mode)
    rprint("Default engine:", s.engine.value)
    rprint("Default quality:", s.quality.value)
