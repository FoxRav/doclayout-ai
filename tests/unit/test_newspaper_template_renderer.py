"""Tests for OCR normalization and newspaper template renderer."""

from __future__ import annotations

from pathlib import Path

from kuvien_parsinta.layout.newspaper_page_model import (
    BlockRole,
    LowerStory,
    MainStory,
    MetaRow,
    NewspaperFrontPageModel,
    OwnershipInfo,
    TextBlock,
    build_newspaper_page_model,
)
from kuvien_parsinta.layout.story_element_detection import StoryContentReport
from kuvien_parsinta.layout.page_layout_builder import build_page_layout
from kuvien_parsinta.markdown.newspaper_markdown import (
    build_newspaper_markdown,
    newspaper_model_to_markdown,
)
from kuvien_parsinta.pdf.newspaper_template_renderer import render_newspaper_template_pdf
from kuvien_parsinta.pdf.structural_newspaper_pdf import (
    extract_visible_pdf_text,
    pdf_contains_full_page_background,
)
from kuvien_parsinta.quality.newspaper_quality_gate import run_newspaper_quality_gate
from kuvien_parsinta.text.ocr_normalization import normalize_ocr_text
from tests.regression.paukku_helpers import build_assembled_paukku_model


def _tb(text: str, role: BlockRole) -> TextBlock:
    return TextBlock(
        text=text,
        bbox=None,
        source_block_ids=(),
        role=role,
        confidence=0.9,
    )


def _sample_model() -> NewspaperFrontPageModel:
    return NewspaperFrontPageModel(
        masthead=_tb("KUVA ERIKOIS", BlockRole.MASTHEAD),
        newspaper_name=_tb("ILTA-SANOMAT", BlockRole.NEWSPAPER_NAME),
        meta=MetaRow(
            issue_number=_tb("N:o 87 — 1976", BlockRole.ISSUE_META),
            date_text=_tb("TIISTAINA HUHTIKUUN 13. PNÄ", BlockRole.DATE_META),
            stars=_tb("***", BlockRole.STARS_META),
            price=_tb("1 mk (sis. lvv)", BlockRole.PRICE_META),
        ),
        main_story=MainStory(
            headline=_tb("JO 39 KUOLONUHRIA", BlockRole.MAIN_HEADLINE),
            subheadline=_tb("TEHDASRÄJÄYKSESSÄ", BlockRole.SECONDARY_HEADLINE),
            hero_image_path=None,
            sidebar_text_blocks=(_tb("Oikean reunan teksti.", BlockRole.RIGHT_SIDEBAR),),
            sidebar_text="Oikean reunan teksti.",
            caption=_tb("Tehdas alueella.", BlockRole.IMAGE_CAPTION),
            missing_required_elements=(),
        ),
        lower_story=LowerStory(
            headline=_tb("LAPUA ERISTETTIIN", BlockRole.LOWER_HEADLINE),
            columns=(_tb("Palsta yksi.", BlockRole.BOTTOM_COLUMN),),
            continuation_marker=_tb("JATKUU TAKASIVULLE", BlockRole.CONTINUATION_BOX),
        ),
        ownership=OwnershipInfo(
            consumed_block_ids=(),
            consumed_metadata_block_ids=(),
            reused_block_ids=(),
            metadata_blocks_consumed_before_story=True,
        ),
        hero_image_crop_path=None,
        story_content=StoryContentReport(
            main_story_sidebar_detected=True,
            image_caption_selected=True,
        ),
    )


def test_normalize_ocr_text_known_corrections() -> None:
    assert "ERISTETTIIN" in normalize_ocr_text("LAPUA ERISTETTHIN")
    assert normalize_ocr_text("kasvol") == "kasvoi"
    assert normalize_ocr_text("vapaehtoiset") == "vapaaehtoiset"


def test_newspaper_model_to_markdown_structure() -> None:
    md = newspaper_model_to_markdown(_sample_model())
    assert "**KUVA ERIKOIS — ILTA-SANOMAT**" in md
    assert "---" in md
    assert "# JO 39 KUOLONUHRIA" in md
    assert "## TEHDASRÄJÄYKSESSÄ" in md
    assert "## LAPUA ERISTETTIIN" in md
    assert "**JATKUU TAKASIVULLE**" in md
    assert md.count("1 mk") == 1


def test_template_renderer_paukku_if_present(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    image = repo / "parsittavat" / "Paukku" / "paukku.jpg"
    structure = repo / "parsittavat" / "Paukku" / "ocr" / "paukku_structurev3_res.json"
    if not structure.is_file():
        structure = repo / "parsittavat" / "Paukku" / "ocr" / "paukku_res.json"
    vl = repo / "parsittavat" / "Paukku" / "ocr" / "paukku_vl_res.json"
    if not image.is_file() or not structure.is_file():
        return

    layout = build_page_layout(
        source_path=image,
        structure_json_path=structure,
        vl_json_path=vl if vl.is_file() else None,
    )
    assert layout is not None

    model = build_assembled_paukku_model(
        layout=layout,
        image=image,
        structure=structure,
        vl=vl if vl.is_file() else None,
        tmp_dir=tmp_path / "crops",
    )
    markdown = build_newspaper_markdown(
        layout=layout,
        vl_json_path=vl if vl.is_file() else None,
        fallback_markdown="fallback",
        model=model,
    )
    assert "JO 39 KUOLONUHRIA" in markdown
    assert "LAPUA ERISTETTIIN" in markdown
    assert markdown.count("1 mk") == 1

    pdf_path = tmp_path / "paukku_structural.pdf"
    style_debug = tmp_path / "ocr" / "paukku_style_debug.json"
    visual_metrics = tmp_path / "ocr" / "paukku_visual_metrics.json"
    _, report, plan = render_newspaper_template_pdf(
        model=model,
        layout=layout,
        pdf_path=pdf_path,
        source_path=image,
        tmp_dir=tmp_path / "crops",
        style_debug_path=style_debug,
        visual_metrics_path=visual_metrics,
    )

    assert report.uses_full_page_background is False
    assert report.hero_image_is_crop is True
    assert pdf_contains_full_page_background(
        pdf_path,
        page_width_pt=layout.pdf_width_pt,
        page_height_pt=layout.pdf_height_pt,
    ) is False

    visible = extract_visible_pdf_text(pdf_path).upper()
    assert "KUOLONUHRIA" in visible
    if plan.masthead_render_mode == "text":
        assert "ILTA-SANOMAT" in visible
    assert "LAPUA" in visible

    (tmp_path / "paukku.md").write_text(markdown, encoding="utf-8-sig")
    gate = run_newspaper_quality_gate(
        stem="paukku",
        target_dir=tmp_path,
        ocr_dir=tmp_path / "ocr",
        markdown_path=tmp_path / "paukku.md",
        structural_pdf_path=pdf_path,
        pdf_width_pt=layout.pdf_width_pt,
        pdf_height_pt=layout.pdf_height_pt,
        emit_facsimile=False,
        page_model=model,
        style_debug_path=style_debug,
        visual_metrics_path=visual_metrics,
        content_audit_path=tmp_path / "ocr" / "paukku_content_audit.json",
    )
    failed = [check.name for check in gate.checks if not check.passed]
    assert gate.passed, f"Quality gate failed: {failed}"
