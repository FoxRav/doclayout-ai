"""PDF output policy: default structural only; optional emit flags."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PdfOutputPlan:
    """Which PDF variants to render for one parse run."""

    structural: bool = True
    facsimile: bool = False
    clean: bool = False
    debug_overlay: bool = False
    debug_search_layer: bool = False


def resolve_pdf_output_plan(
    *,
    pdf_mode: str,
    emit_facsimile: bool,
    emit_clean: bool,
    emit_debug_pdf: bool,
) -> PdfOutputPlan:
    """Normal runs emit structural only; extras require explicit flags."""
    normalized = "structural" if pdf_mode == "rebuild" else pdf_mode
    if normalized == "all":
        return PdfOutputPlan(
            structural=True,
            facsimile=emit_facsimile,
            clean=emit_clean,
            debug_overlay=emit_debug_pdf,
            debug_search_layer=emit_debug_pdf,
        )
    if normalized == "facsimile":
        return PdfOutputPlan(
            structural=True,
            facsimile=emit_facsimile,
            clean=emit_clean,
            debug_overlay=emit_debug_pdf,
            debug_search_layer=emit_debug_pdf,
        )
    if normalized == "clean":
        return PdfOutputPlan(
            structural=False,
            facsimile=False,
            clean=True,
            debug_overlay=emit_debug_pdf,
            debug_search_layer=emit_debug_pdf,
        )
    return PdfOutputPlan(
        structural=True,
        facsimile=emit_facsimile,
        clean=emit_clean,
        debug_overlay=emit_debug_pdf,
        debug_search_layer=emit_debug_pdf,
    )
