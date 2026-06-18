"""Simple quality gate for newspaper parse outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import fitz

from kuvien_parsinta.layout.newspaper_page_model import NewspaperFrontPageModel
from kuvien_parsinta.markdown.newspaper_markdown import extract_story_body
from kuvien_parsinta.pdf.structural_newspaper_pdf import pdf_contains_full_page_background

_CONTENT_CHECK_NAMES = frozenset(
    {
        "content_quality_pass",
        "content_loss_not_detected",
        "content_misassignment_not_detected",
        "truncated_text_not_detected",
        "duplicate_text_not_detected",
        "quality_result_not_fail",
        "quality_result_full_pass",
    }
)
_SOFT_QUALITY_CHECK_NAMES = frozenset(
    {
        "headline_to_hero_gap_visual_warning",
        "hero_to_caption_gap_visual_warning",
        "total_vertical_whitespace_visual_warning",
        "caption_to_lower_headline_gap_visual_warning",
        "lower_headline_to_columns_gap_visual_warning",
        "masthead_similarity_visual_warning",
        "text_cleanup_pass",
        "bottom_columns_readability_warn",
    }
)
_MIDDLE_ZONE_Y = (0.28, 0.75)
_ZONE_EPSILON = 0.02
_HEADLINE_ZONE_Y = (0.185, 0.335)
_MASTHEAD_ZONE_Y = (0.025, 0.135)
_BOTTOM_HEADLINE_ZONE_Y = (0.765, 0.835)


@dataclass(frozen=True, slots=True)
class QualityCheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class QualityGateResult:
    passed: bool
    checks: tuple[QualityCheck, ...]
    status: str = "pass"
    content_metrics: dict[str, object] | None = None

    def to_json_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "passed": self.passed,
            "status": self.status,
            "checks": [
                {"name": check.name, "passed": check.passed, "detail": check.detail}
                for check in self.checks
            ],
        }
        if self.content_metrics is not None:
            payload.update(self.content_metrics)
        return payload


def run_newspaper_quality_gate(
    *,
    stem: str,
    target_dir: Path,
    ocr_dir: Path,
    markdown_path: Path,
    structural_pdf_path: Path | None,
    pdf_width_pt: float,
    pdf_height_pt: float,
    emit_facsimile: bool,
    page_model: NewspaperFrontPageModel | None = None,
    style_debug_path: Path | None = None,
    visual_metrics_path: Path | None = None,
    content_audit_path: Path | None = None,
) -> QualityGateResult:
    """Run minimal quality checks for newspaper parse output."""
    checks: list[QualityCheck] = []
    content_metrics: dict[str, object] | None = None

    checks.append(
        QualityCheck(
            name="markdown_exists",
            passed=markdown_path.is_file() and markdown_path.stat().st_size > 0,
        )
    )
    checks.append(
        QualityCheck(
            name="structural_pdf_exists",
            passed=structural_pdf_path is not None
            and structural_pdf_path.is_file()
            and structural_pdf_path.stat().st_size > 0,
        )
    )
    checks.append(
        QualityCheck(
            name="no_test_pdf_in_root",
            passed=len(list(target_dir.glob("*_test.pdf"))) == 0,
        )
    )
    checks.append(
        QualityCheck(
            name="no_facsimile_in_root",
            passed=len(list(target_dir.glob("*_facsimile*.pdf"))) == 0,
        )
    )
    if not emit_facsimile:
        checks.append(
            QualityCheck(
                name="no_facsimile_in_ocr_by_default",
                passed=len(list(ocr_dir.glob("*_facsimile*.pdf"))) == 0,
            )
        )

    if structural_pdf_path is not None and structural_pdf_path.is_file():
        checks.append(
            QualityCheck(
                name="no_full_page_background",
                passed=not pdf_contains_full_page_background(
                    structural_pdf_path,
                    page_width_pt=pdf_width_pt,
                    page_height_pt=pdf_height_pt,
                ),
            )
        )
        layout_checks = _verify_pdf_layout(
            structural_pdf_path,
            page_height_pt=pdf_height_pt,
        )
        checks.extend(layout_checks)

    if markdown_path.is_file():
        md_text = markdown_path.read_text(encoding="utf-8-sig")
        md_upper = md_text.upper()
        for phrase in ("JO 39 KUOLONUHRIA", "TEHDASRÄJÄYKSESSÄ", "LAPUA ERISTETTIIN"):
            checks.append(
                QualityCheck(
                    name=f"markdown_contains_{phrase.replace(' ', '_').lower()}",
                    passed=phrase.upper() in md_upper or phrase.replace("Ä", "A") in md_upper,
                )
            )
        checks.extend(_verify_metadata_ownership(md_text, page_model))
        checks.extend(_verify_typography(style_debug_path, page_model, structural_pdf_path))
        checks.extend(_verify_visual_layout(visual_metrics_path, style_debug_path))
        pdf_for_cleanup = _read_pdf_text(structural_pdf_path)
        checks.extend(_verify_text_cleanup(md_text, pdf_for_cleanup, page_model))
        if structural_pdf_path is not None and visual_metrics_path is not None:
            checks.extend(
                _verify_text_crop_policy(
                    visual_metrics_path=visual_metrics_path,
                    structural_pdf_path=structural_pdf_path,
                )
            )
        story_checks, content_metrics = _verify_required_story_content(
            page_model=page_model,
            structural_pdf_path=structural_pdf_path,
            markdown_path=markdown_path,
        )
        checks.extend(story_checks)
    else:
        content_metrics = None

    if page_model is not None and content_metrics is None:
        _, content_metrics = _verify_required_story_content(
            page_model=page_model,
            structural_pdf_path=structural_pdf_path,
            markdown_path=markdown_path if markdown_path.is_file() else None,
        )

    if visual_metrics_path is not None and visual_metrics_path.is_file():
        vm = json.loads(visual_metrics_path.read_text(encoding="utf-8"))
        crop_metrics: dict[str, object] = {
            "text_crops_used": bool(vm.get("text_crops_used", True)),
            "photo_crops_used": bool(vm.get("photo_crops_used", False)),
            "forbidden_text_crop_blocks": list(vm.get("forbidden_text_crop_blocks", [])),
            "masthead_render_mode": str(vm.get("masthead_render_mode", "text")),
            "newspaper_name_render_mode": str(vm.get("newspaper_name_render_mode", "text")),
            "headlines_render_mode": str(vm.get("headlines_render_mode", "text")),
            "metadata_render_mode": str(vm.get("metadata_render_mode", "text")),
            "caption_render_mode": str(vm.get("caption_render_mode", "text")),
            "continuation_text_render_mode": str(vm.get("continuation_text_render_mode", "text")),
        }
        if content_metrics is None:
            content_metrics = crop_metrics
        else:
            content_metrics = {**content_metrics, **crop_metrics}

    layout_quality = "PASS"
    layout_hard_fail = any(
        not check.passed
        for check in checks
        if not _is_soft_quality_check(check.name)
        and not check.name.startswith("content_")
        and check.name not in _CONTENT_CHECK_NAMES
    )
    if layout_hard_fail:
        layout_quality = "FAIL"

    from kuvien_parsinta.quality.content_audit import run_content_audit, save_content_audit

    content_audit = run_content_audit(
        page_model=page_model,
        markdown_path=markdown_path if markdown_path.is_file() else None,
        structural_pdf_path=structural_pdf_path,
        layout_quality=layout_quality,
    )
    if content_audit_path is not None:
        save_content_audit(result=content_audit, output_path=content_audit_path)

    checks.extend(_content_audit_checks(content_audit))
    audit_metrics: dict[str, object] = {
        "layout_quality": content_audit.layout_quality,
        "content_quality": content_audit.content_quality,
        "quality_result": content_audit.quality_result,
        "content_loss_detected": content_audit.content_loss_detected,
        "content_misassignment_detected": content_audit.content_misassignment_detected,
        "truncated_text_detected": content_audit.truncated_text_detected,
        "duplicate_text_detected": content_audit.duplicate_text_detected,
    }
    if content_metrics is None:
        content_metrics = audit_metrics
    else:
        content_metrics = {**content_metrics, **audit_metrics}

    hard_fail = layout_hard_fail or content_audit.content_quality == "FAIL"
    soft_warnings = [
        check
        for check in checks
        if not check.passed and _is_soft_quality_check(check.name)
    ]
    finishing_fail = any(
        check.name == "bottom_columns_readability_fail" and not check.passed for check in checks
    )
    if hard_fail or finishing_fail:
        status = "fail"
        passed = False
        quality_result = "FAIL"
    elif soft_warnings:
        status = "pass_with_warnings"
        passed = True
        quality_result = "PASS_WITH_WARNINGS"
    else:
        status = "pass"
        passed = True
        quality_result = "PASS"

    bottom_readability = _bottom_columns_readability_from_checks(checks)
    text_cleanup_pass = all(
        check.passed for check in checks if check.name == "text_cleanup_pass"
    ) if any(check.name == "text_cleanup_pass" for check in checks) else True
    masthead_similarity_warning = any(
        check.name == "masthead_similarity_visual_warning" and not check.passed
        for check in checks
    )

    if content_metrics is None:
        content_metrics = {}
    content_metrics.update(
        {
            "quality_result": quality_result,
            "bottom_columns_readability": bottom_readability,
            "text_cleanup_pass": text_cleanup_pass,
            "visual_finishing_quality": (
                "FAIL"
                if finishing_fail
                else ("WARN" if soft_warnings else "PASS")
            ),
            "masthead_similarity_warning": masthead_similarity_warning,
        }
    )

    return QualityGateResult(
        passed=passed,
        checks=tuple(checks),
        status=status,
        content_metrics=content_metrics,
    )


def _verify_metadata_ownership(
    markdown: str,
    page_model: NewspaperFrontPageModel | None,
) -> list[QualityCheck]:
    checks: list[QualityCheck] = []
    body = extract_story_body(markdown).upper()
    sidebar = (
        page_model.right_sidebar_text.upper()
        if page_model is not None
        else body
    )

    price_count = markdown.upper().count("1 MK")
    checks.append(
        QualityCheck(
            name="price_meta_exists",
            passed=page_model is not None and "MK" in page_model.price_text.upper(),
        )
    )
    checks.append(
        QualityCheck(
            name="price_occurrences_in_markdown",
            passed=price_count == 1,
            detail=f"count={price_count}",
        )
    )
    checks.append(
        QualityCheck(
            name="price_occurrences_in_sidebar",
            passed="1 MK" not in sidebar and "(SIS." not in sidebar[:40],
        )
    )
    checks.append(
        QualityCheck(
            name="stars_occurrences_in_body",
            passed="***" not in body and "☆" not in body,
        )
    )
    checks.append(
        QualityCheck(
            name="issue_number_occurrences_in_body",
            passed="N:O" not in body and "N:O" not in body.replace(" ", ""),
        )
    )
    checks.append(
        QualityCheck(
            name="date_occurrences_in_body",
            passed="PNÄ" not in body and "HUHTIKUUN" not in body,
        )
    )
    checks.append(
        QualityCheck(
            name="metadata_blocks_consumed_before_story",
            passed=(
                page_model is not None
                and page_model.ownership.metadata_blocks_consumed_before_story
            ),
        )
    )
    checks.append(
        QualityCheck(
            name="no_consumed_block_reused",
            passed=(
                page_model is not None and len(page_model.ownership.reused_block_ids) == 0
            ),
            detail=(
                f"reused={list(page_model.ownership.reused_block_ids)}"
                if page_model is not None
                else ""
            ),
        )
    )
    if page_model is not None:
        checks.append(
            QualityCheck(
                name="price_text_in_page_model",
                passed="1 MK" in page_model.price_text.upper(),
            )
        )
        sidebar_start = page_model.right_sidebar_text.strip()[:20].upper()
        checks.append(
            QualityCheck(
                name="sidebar_does_not_start_with_price",
                passed=not sidebar_start.startswith("1 MK") and "SIS." not in sidebar_start,
            )
        )
    return checks


def _verify_visual_layout(
    visual_metrics_path: Path | None,
    style_debug_path: Path | None = None,
) -> list[QualityCheck]:
    if visual_metrics_path is None or not visual_metrics_path.is_file():
        return [QualityCheck(name="visual_metrics_exists", passed=False)]

    payload = json.loads(visual_metrics_path.read_text(encoding="utf-8"))
    checks = [QualityCheck(name="visual_metrics_exists", passed=True)]
    checks.append(
        QualityCheck(
            name="masthead_overlap",
            passed=not bool(payload.get("masthead_overlap", True)),
        )
    )
    checks.append(
        QualityCheck(
            name="hero_image_width_ratio_gte_0_70",
            passed=float(payload.get("hero_image_width_ratio", 0)) >= 0.70,
            detail=str(payload.get("hero_image_width_ratio")),
        )
    )
    checks.append(
        QualityCheck(
            name="right_sidebar_width_ratio_gte_0_18",
            passed=float(payload.get("right_sidebar_width_ratio", 0)) >= 0.18,
            detail=str(payload.get("right_sidebar_width_ratio")),
        )
    )
    bottom_font = float(payload.get("bottom_column_font_size", 0))
    checks.append(
        QualityCheck(
            name="bottom_column_font_size_gte_5_5",
            passed=bottom_font >= 5.5,
            detail=str(bottom_font),
        )
    )
    if bottom_font < 5.5:
        checks.append(
            QualityCheck(
                name="bottom_columns_readability_fail",
                passed=False,
                detail=f"font_size={bottom_font}",
            )
        )
    headline_gap = float(
        payload.get("headline_to_hero_gap_ratio", payload.get("headline_to_image_gap_ratio", 1.0))
    )
    checks.append(
        QualityCheck(
            name="headline_to_hero_gap_visual_warning",
            passed=headline_gap <= 0.045,
            detail=f"gap={headline_gap}",
        )
    )
    caption_gap = float(
        payload.get("hero_to_caption_gap_ratio", payload.get("image_to_caption_gap_ratio", 1.0))
    )
    checks.append(
        QualityCheck(
            name="hero_to_caption_gap_visual_warning",
            passed=caption_gap <= 0.022,
            detail=f"gap={caption_gap}",
        )
    )
    lower_gap = float(payload.get("caption_to_lower_headline_gap_ratio", 1.0))
    checks.append(
        QualityCheck(
            name="caption_to_lower_headline_gap_visual_warning",
            passed=lower_gap <= 0.035,
            detail=f"gap={lower_gap}",
        )
    )
    columns_gap = float(payload.get("lower_headline_to_columns_gap_ratio", 1.0))
    checks.append(
        QualityCheck(
            name="lower_headline_to_columns_gap_visual_warning",
            passed=columns_gap <= 0.025,
            detail=f"gap={columns_gap}",
        )
    )
    whitespace = float(
        payload.get(
            "total_vertical_whitespace_ratio",
            payload.get("vertical_whitespace_ratio", 1.0),
        )
    )
    checks.append(
        QualityCheck(
            name="total_vertical_whitespace_visual_warning",
            passed=whitespace <= 0.15,
            detail=f"whitespace={whitespace}",
        )
    )
    masthead_mode = str(payload.get("masthead_render_mode", "text"))
    checks.append(
        QualityCheck(
            name="masthead_render_mode_ok",
            passed=masthead_mode == "text" and not bool(payload.get("masthead_overlap", False)),
            detail=f"mode={masthead_mode}",
        )
    )
    overflow_bottom = False
    if style_debug_path is not None and style_debug_path.is_file():
        style_payload = json.loads(style_debug_path.read_text(encoding="utf-8"))
        if bool(style_payload.get("masthead_similarity_warning", False)):
            checks.append(
                QualityCheck(
                    name="masthead_similarity_visual_warning",
                    passed=False,
                    detail="masthead_similarity_warning",
                )
            )
        overflow_bottom = any(
            "bottom_column" in item for item in list(style_payload.get("overflow_warnings", []))
        )
    if bottom_font >= 5.5 and overflow_bottom:
        checks.append(
            QualityCheck(
                name="bottom_columns_readability_warn",
                passed=False,
                detail="bottom_column_overflow",
            )
        )
    for warn in list(payload.get("warnings", [])):
        checks.append(
            QualityCheck(
                name=f"visual_layout_{warn}_warning",
                passed=False,
                detail=warn,
            )
        )
    return checks


def _verify_text_cleanup(
    markdown: str,
    pdf_text: str,
    page_model: NewspaperFrontPageModel | None,
) -> list[QualityCheck]:
    from kuvien_parsinta.text.final_text_cleanup import text_cleanup_issues

    blob_parts = [markdown, pdf_text]
    if page_model is not None:
        blob_parts.extend(
            [
                page_model.right_sidebar_text,
                page_model.image_caption,
                page_model.price_text,
                "\n".join(page_model.bottom_column_texts),
            ]
        )
    blob = "\n".join(part for part in blob_parts if part)
    issues = text_cleanup_issues(blob)
    checks = [
        QualityCheck(
            name="text_cleanup_pass",
            passed=len(issues) == 0,
            detail=",".join(issues),
        )
    ]
    for issue in issues:
        checks.append(
            QualityCheck(
                name=f"text_cleanup_{issue}_visual_warning",
                passed=False,
                detail=issue,
            )
        )
    return checks


def _verify_text_crop_policy(
    *,
    visual_metrics_path: Path | None = None,
    structural_pdf_path: Path | None = None,
    payload: dict[str, object] | None = None,
) -> list[QualityCheck]:
    from kuvien_parsinta.pdf.structural_newspaper_pdf import count_embedded_images

    if payload is None:
        if visual_metrics_path is None or not visual_metrics_path.is_file():
            return [QualityCheck(name="text_crop_policy_metrics", passed=False)]
        payload = json.loads(visual_metrics_path.read_text(encoding="utf-8"))

    checks: list[QualityCheck] = []
    text_crops_used = bool(payload.get("text_crops_used", True))
    photo_crops_used = bool(payload.get("photo_crops_used", False))
    forbidden = list(payload.get("forbidden_text_crop_blocks", []))
    masthead_mode = str(payload.get("masthead_render_mode", "text"))
    newspaper_mode = str(payload.get("newspaper_name_render_mode", "text"))

    checks.append(
        QualityCheck(
            name="text_crops_used",
            passed=not text_crops_used,
            detail=str(text_crops_used),
        )
    )
    checks.append(
        QualityCheck(
            name="photo_crops_used",
            passed=photo_crops_used,
            detail=str(photo_crops_used),
        )
    )
    checks.append(
        QualityCheck(
            name="forbidden_text_crop_blocks_empty",
            passed=len(forbidden) == 0,
            detail=str(forbidden),
        )
    )
    checks.append(
        QualityCheck(
            name="masthead_render_mode_text",
            passed=masthead_mode == "text",
            detail=masthead_mode,
        )
    )
    checks.append(
        QualityCheck(
            name="newspaper_name_render_mode_text",
            passed=newspaper_mode == "text",
            detail=newspaper_mode,
        )
    )

    if structural_pdf_path is not None and structural_pdf_path.is_file():
        pdf_text = _read_pdf_text(structural_pdf_path).upper()
        for phrase in (
            "ILTA-SANOMAT",
            "JO 39 KUOLONUHRIA",
            "TEHDASR",
            "LAPUA ERISTET",
            "JATKUU",
        ):
            checks.append(
                QualityCheck(
                    name=f"pdf_text_contains_{phrase.replace(' ', '_').lower()}",
                    passed=phrase in pdf_text or phrase.replace("Ä", "A") in pdf_text,
                )
            )
        image_count = count_embedded_images(structural_pdf_path)
        checks.append(
            QualityCheck(
                name="structural_pdf_only_photo_crops",
                passed=1 <= image_count <= 2,
                detail=f"images={image_count}",
            )
        )
    return checks


def _verify_required_story_content(
    *,
    page_model: NewspaperFrontPageModel | None,
    structural_pdf_path: Path | None,
    markdown_path: Path | None,
) -> tuple[list[QualityCheck], dict[str, object]]:
    if page_model is None:
        return [], {}

    story = page_model.story_content
    sidebar_text = page_model.right_sidebar_text.strip()
    caption_text = page_model.image_caption.strip()
    pdf_text = _read_pdf_text(structural_pdf_path)
    pdf_upper = pdf_text.upper()
    pdf_lower = pdf_text.lower()

    sidebar_detected = story.main_story_sidebar_detected or bool(sidebar_text)
    sidebar_rendered = True
    if sidebar_text:
        sidebar_rendered = (
            sidebar_text[:24].upper() in pdf_upper
            or "JO 39" in pdf_upper
            or "LÖYDETTY KUOLE" in pdf_upper.replace("Ö", "O")
        )

    caption_selected = bool(caption_text)
    caption_rendered = True
    if caption_text:
        caption_rendered = (
            "MURHE" in pdf_upper
            or caption_text[:20].lower() in pdf_lower
            or "UHRIEN" in pdf_upper
        )
    elif story.image_caption_candidates_count > 0:
        caption_rendered = False

    markdown_has_caption = True
    if caption_text and markdown_path is not None and markdown_path.is_file():
        md_lower = markdown_path.read_text(encoding="utf-8-sig").lower()
        markdown_has_caption = (
            "kuvateksti:" in md_lower and caption_text[:15].lower() in md_lower
        )

    content_loss = (
        story.content_loss_detected
        or (sidebar_detected and not sidebar_text)
        or (sidebar_text and not sidebar_rendered)
        or (story.image_caption_candidates_count > 0 and not caption_selected)
        or (caption_selected and not caption_rendered)
    )

    metrics: dict[str, object] = {
        "main_story_sidebar_detected": sidebar_detected,
        "main_story_sidebar_rendered": sidebar_rendered,
        "image_caption_candidates_count": story.image_caption_candidates_count,
        "image_caption_selected": caption_selected,
        "image_caption_rendered": caption_rendered,
        "content_loss_detected": content_loss,
    }

    checks = [
        QualityCheck(
            name="main_story_sidebar_in_page_model",
            passed=bool(sidebar_text) or not sidebar_detected,
            detail=sidebar_text[:60] if sidebar_text else "",
        ),
        QualityCheck(
            name="main_story_sidebar_rendered_in_pdf",
            passed=not sidebar_text or sidebar_rendered,
        ),
        QualityCheck(
            name="image_caption_selected_when_candidates_exist",
            passed=story.image_caption_candidates_count == 0 or caption_selected,
            detail=f"candidates={story.image_caption_candidates_count}",
        ),
        QualityCheck(
            name="image_caption_rendered_in_pdf",
            passed=not caption_text or caption_rendered,
        ),
        QualityCheck(
            name="markdown_contains_image_caption",
            passed=not caption_text or markdown_has_caption,
        ),
    ]
    if caption_text:
        checks.append(
            QualityCheck(
                name="caption_contains_murhe",
                passed="murhe" in caption_text.lower(),
            )
        )
    if sidebar_text:
        checks.append(
            QualityCheck(
                name="sidebar_not_truncated_at_vapaaehtoiset",
                passed=not sidebar_text.rstrip().endswith("vapaaehtoiset"),
                detail=sidebar_text[-40:],
            )
        )
    checks.append(
        QualityCheck(
            name="content_loss_detected",
            passed=not content_loss,
            detail=str(list(page_model.main_story.missing_required_elements)),
        ),
    )
    return checks, metrics


def _read_pdf_text(pdf_path: Path | None) -> str:
    if pdf_path is None or not pdf_path.is_file():
        return ""
    doc = fitz.open(str(pdf_path))
    try:
        return doc[0].get_text()
    finally:
        doc.close()


def _verify_typography(
    style_debug_path: Path | None,
    page_model: NewspaperFrontPageModel | None,
    structural_pdf_path: Path | None,
) -> list[QualityCheck]:
    checks: list[QualityCheck] = []
    if style_debug_path is None or not style_debug_path.is_file():
        checks.append(QualityCheck(name="style_debug_exists", passed=False))
        return checks

    payload = json.loads(style_debug_path.read_text(encoding="utf-8"))
    headline = float(payload.get("headline_font_size", 0))
    lower = float(payload.get("lower_headline_font_size", 0))
    body = float(payload.get("body_font_size", 0))
    caption = float(payload.get("caption_font_size", 0))
    bottom = float(payload.get("bottom_column_font_size", 0))
    masthead_mode = str(payload.get("masthead_render_mode", "text"))
    warnings_list = list(payload.get("warnings", []))
    overflow = list(payload.get("overflow_warnings", []))

    checks.append(QualityCheck(name="style_debug_exists", passed=True))
    checks.append(
        QualityCheck(
            name="main_headline_font_size_gt_3x_body",
            passed=headline > body * 3 if body > 0 else False,
            detail=f"headline={headline}, body={body}",
        )
    )
    checks.append(
        QualityCheck(
            name="lower_headline_font_size_gt_2x_body",
            passed=lower > body * 2 if body > 0 else False,
            detail=f"lower={lower}, body={body}",
        )
    )
    checks.append(
        QualityCheck(
            name="caption_font_size_lte_body",
            passed=caption <= body if body > 0 else True,
            detail=f"caption={caption}, body={body}",
        )
    )
    checks.append(
        QualityCheck(
            name="bottom_column_font_size_gte_minimum",
            passed=bottom >= 5.5,
            detail=f"bottom={bottom}",
        )
    )
    checks.append(
        QualityCheck(
            name="masthead_not_plain_body_font",
            passed=masthead_mode == "text",
            detail=f"mode={masthead_mode}",
        )
    )
    if page_model is not None and page_model.main_story.caption is not None:
        checks.append(
            QualityCheck(
                name="image_caption_exists_when_vl_found",
                passed=bool(page_model.image_caption.strip()),
            )
        )
    for item in overflow:
        checks.append(
            QualityCheck(
                name="bottom_column_overflow_warning",
                passed=False,
                detail=item,
            )
        )
    for warn in warnings_list:
        checks.append(
            QualityCheck(
                name=f"typography_{warn}_warning",
                passed=False,
                detail=warn,
            )
        )
    if structural_pdf_path is not None and structural_pdf_path.is_file():
        checks.append(_check_continuation_box_colors(structural_pdf_path))
    return checks


def _check_continuation_box_colors(pdf_path: Path) -> QualityCheck:
    doc = fitz.open(str(pdf_path))
    try:
        page = doc[0]
        has_white_on_black = False
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                text = "".join(span.get("text", "") for span in line.get("spans", []))
                if "JATKUU" not in text.upper():
                    continue
                for span in line.get("spans", []):
                    if span.get("color", 0) == 16777215:
                        has_white_on_black = True
        return QualityCheck(
            name="continuation_box_white_text",
            passed=has_white_on_black,
        )
    finally:
        doc.close()


def save_quality_report(*, result: QualityGateResult, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.to_json_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def append_error_log(*, output_path: Path, error_id: str, message: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    entry = json.dumps({"error_id": error_id, "message": message}, ensure_ascii=False)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(entry + "\n")


def _verify_pdf_layout(pdf_path: Path, *, page_height_pt: float) -> list[QualityCheck]:
    doc = fitz.open(str(pdf_path))
    try:
        page = doc[0]
        text_items = _text_positions(page, page_height_pt)
        image_items = _image_positions(page, page_height_pt)

        main_y = _find_text_y(text_items, ("KUOLONUHRIA", "JO 39"))
        secondary_y = _find_text_y(text_items, ("TEHDASR", "YKSESS"))
        masthead_y = _find_text_y(text_items, ("ILTA-SANOMAT", "KUVA ERIKOIS"))
        bottom_headline_y = _find_text_y(text_items, ("LAPUA ERISTETTI", "ERISTETTIIN"))
        hero_y = _hero_image_y_norm(page, page_height_pt)

        checks: list[QualityCheck] = []
        if hero_y is not None:
            checks.append(
                QualityCheck(
                    name="hero_image_in_middle_zone",
                    passed=(
                        _MIDDLE_ZONE_Y[0] - _ZONE_EPSILON
                        <= hero_y
                        <= _MIDDLE_ZONE_Y[1] + _ZONE_EPSILON
                    ),
                    detail=f"hero_y={hero_y:.3f}",
                )
            )
        if main_y is not None and hero_y is not None:
            checks.append(
                QualityCheck(
                    name="main_headline_above_hero",
                    passed=main_y < hero_y,
                    detail=f"main_y={main_y:.3f}, hero_y={hero_y:.3f}",
                )
            )
        if secondary_y is not None and hero_y is not None:
            checks.append(
                QualityCheck(
                    name="secondary_headline_above_hero",
                    passed=secondary_y < hero_y,
                    detail=f"secondary_y={secondary_y:.3f}, hero_y={hero_y:.3f}",
                )
            )
        if bottom_headline_y is not None and hero_y is not None:
            checks.append(
                QualityCheck(
                    name="bottom_headline_below_hero",
                    passed=bottom_headline_y > hero_y,
                    detail=f"bottom_y={bottom_headline_y:.3f}, hero_y={hero_y:.3f}",
                )
            )
        if masthead_y is not None and main_y is not None:
            checks.append(
                QualityCheck(
                    name="masthead_above_headline",
                    passed=masthead_y < main_y,
                    detail=f"masthead_y={masthead_y:.3f}, main_y={main_y:.3f}",
                )
            )
        return checks
    finally:
        doc.close()


def _text_positions(page: fitz.Page, page_height_pt: float) -> list[tuple[str, float]]:
    items: list[tuple[str, float]] = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", []))
            if not text.strip():
                continue
            y_norm = line["bbox"][1] / page_height_pt
            items.append((text.upper(), y_norm))
    return items


def _image_positions(page: fitz.Page, page_height_pt: float) -> list[tuple[str, float]]:
    items: list[tuple[str, float]] = []
    for image in page.get_images(full=True):
        xref = int(image[0])
        for rect in page.get_image_rects(xref):
            y_norm = rect.y0 / page_height_pt
            items.append(("image", y_norm))
    return items


def _hero_image_y_norm(page: fitz.Page, page_height_pt: float) -> float | None:
    best_area = 0.0
    best_y: float | None = None
    for image in page.get_images(full=True):
        xref = int(image[0])
        for rect in page.get_image_rects(xref):
            area = rect.width * rect.height
            if area > best_area:
                best_area = area
                best_y = rect.y0 / page_height_pt
    return best_y


def _find_text_y(items: list[tuple[str, float]], needles: tuple[str, ...]) -> float | None:
    for text, y in items:
        for needle in needles:
            if needle in text:
                return y
    return None


def _content_audit_checks(audit: object) -> list[QualityCheck]:
    from kuvien_parsinta.quality.content_audit import ContentAuditResult

    if not isinstance(audit, ContentAuditResult):
        return []
    return [
        QualityCheck(
            name="content_quality_pass",
            passed=audit.content_quality == "PASS",
            detail=audit.content_quality,
        ),
        QualityCheck(
            name="content_loss_not_detected",
            passed=not audit.content_loss_detected,
        ),
        QualityCheck(
            name="content_misassignment_not_detected",
            passed=not audit.content_misassignment_detected,
        ),
        QualityCheck(
            name="truncated_text_not_detected",
            passed=not audit.truncated_text_detected,
        ),
        QualityCheck(
            name="duplicate_text_not_detected",
            passed=not audit.duplicate_text_detected,
        ),
        QualityCheck(
            name="quality_result_not_fail",
            passed=audit.quality_result != "FAIL",
            detail=audit.quality_result,
        ),
        QualityCheck(
            name="quality_result_full_pass",
            passed=audit.quality_result == "PASS",
            detail=audit.quality_result,
        ),
    ]


def is_soft_quality_check(name: str) -> bool:
    """Return True when a failed check should warn instead of hard-failing."""
    return _is_soft_quality_check(name)


def _is_soft_quality_check(name: str) -> bool:
    if name in _SOFT_QUALITY_CHECK_NAMES:
        return True
    if name.endswith("_warning") or name.endswith("_visual_warning"):
        return True
    return name in {
        "headline_to_image_gap_not_too_large",
        "image_to_caption_gap_small",
        "vertical_whitespace_not_excessive",
    }


def _bottom_columns_readability_from_checks(checks: tuple[QualityCheck, ...]) -> str:
    if any(check.name == "bottom_columns_readability_fail" and not check.passed for check in checks):
        return "FAIL"
    if any(check.name == "bottom_columns_readability_warn" and not check.passed for check in checks):
        return "WARN"
    return "PASS"
