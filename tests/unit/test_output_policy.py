"""Default parse output emits structural PDF only."""

from __future__ import annotations

from kuvien_parsinta.pdf.output_policy import resolve_pdf_output_plan


def test_default_output_plan_structural_only() -> None:
    plan = resolve_pdf_output_plan(
        pdf_mode="structural",
        emit_facsimile=False,
        emit_clean=False,
        emit_debug_pdf=False,
    )
    assert plan.structural is True
    assert plan.facsimile is False
    assert plan.clean is False
    assert plan.debug_overlay is False
    assert plan.debug_search_layer is False


def test_emit_flags_enable_optional_pdfs() -> None:
    plan = resolve_pdf_output_plan(
        pdf_mode="structural",
        emit_facsimile=True,
        emit_clean=True,
        emit_debug_pdf=True,
    )
    assert plan.structural is True
    assert plan.facsimile is True
    assert plan.clean is True
    assert plan.debug_overlay is True
    assert plan.debug_search_layer is True


def test_pdf_mode_all_does_not_emit_extras_without_flags() -> None:
    plan = resolve_pdf_output_plan(
        pdf_mode="all",
        emit_facsimile=False,
        emit_clean=False,
        emit_debug_pdf=False,
    )
    assert plan.structural is True
    assert plan.facsimile is False
    assert plan.clean is False
