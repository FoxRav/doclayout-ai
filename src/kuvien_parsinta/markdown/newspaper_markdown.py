"""Structured newspaper markdown from NewspaperFrontPageModel."""

from __future__ import annotations

from pathlib import Path

from kuvien_parsinta.layout.newspaper_page_model import (
    NewspaperFrontPageModel,
    NewspaperPageModel,
    build_newspaper_page_model,
)
from kuvien_parsinta.layout.page_layout import DocumentType, PageLayout
from kuvien_parsinta.text.final_text_cleanup import cleanup_final_text


def newspaper_model_to_markdown(model: NewspaperFrontPageModel) -> str:
    """Build primary markdown from content model — metadata before story body."""
    parts: list[str] = []

    parts.append(f"**{model.masthead_text} — {model.newspaper_name_text}**")
    parts.append("")
    if model.issue_number.strip():
        parts.append(model.issue_number)
    if model.date_text.strip():
        parts.append(model.date_text)
    parts.append("")
    parts.append("---")
    parts.append("")
    if model.price_text.strip():
        parts.append(model.price_text)
    parts.append("")
    parts.append(f"# {cleanup_final_text(model.main_headline)}")
    parts.append("")
    if model.secondary_headline.strip():
        parts.append(f"## {cleanup_final_text(model.secondary_headline)}")

    if model.right_sidebar_text.strip():
        parts.append("")
        parts.append(cleanup_final_text(model.right_sidebar_text))

    if model.image_caption.strip():
        parts.append("")
        parts.append(f"*Kuvateksti: {cleanup_final_text(model.image_caption)}*")

    parts.append("")
    parts.append(f"## {cleanup_final_text(model.bottom_headline)}")
    for col_text in model.bottom_column_texts:
        if col_text.strip():
            parts.append("")
            parts.append(cleanup_final_text(col_text))
    if model.continuation_text.strip():
        parts.append("")
        parts.append(f"**{model.continuation_text}**")

    return "\n".join(parts).strip()


def extract_story_body(markdown: str) -> str:
    """Return main-story body text (sidebar) — excludes metadata and headlines."""
    lines = markdown.splitlines()
    body_lines: list[str] = []
    in_body = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") and "TEHDASR" in stripped.upper():
            in_body = True
            continue
        if not in_body:
            continue
        if stripped.startswith("## ") or stripped.startswith("*Kuvateksti"):
            break
        if stripped.startswith("#"):
            continue
        body_lines.append(line)
    return "\n".join(body_lines).strip()


def build_newspaper_markdown(
    *,
    layout: PageLayout,
    vl_json_path: Path | None,
    fallback_markdown: str,
    source_path: Path | None = None,
    tmp_dir: Path | None = None,
    model: NewspaperPageModel | None = None,
) -> str:
    """Build primary markdown from NewspaperFrontPageModel."""
    page_model = model
    if page_model is None:
        if source_path is None:
            return fallback_markdown.strip()
        page_model = build_newspaper_page_model(
            layout=layout,
            source_path=source_path,
            vl_json_path=vl_json_path,
            tmp_dir=tmp_dir,
        )
    markdown = newspaper_model_to_markdown(page_model)
    markdown = cleanup_final_text(markdown)
    if not markdown:
        return fallback_markdown.strip()
    return markdown


def resolve_primary_markdown(
    *,
    engine_markdown: str,
    layout: PageLayout | None,
    vl_json_path: Path | None,
    source_path: Path | None = None,
    tmp_dir: Path | None = None,
    newspaper_model: NewspaperPageModel | None = None,
) -> str:
    """Choose primary markdown source (newspaper model vs engine fallback)."""
    if layout is not None and layout.document_type is DocumentType.NEWSPAPER_FRONT_PAGE:
        text = build_newspaper_markdown(
            layout=layout,
            vl_json_path=vl_json_path,
            fallback_markdown=engine_markdown,
            source_path=source_path,
            tmp_dir=tmp_dir,
            model=newspaper_model,
        )
    else:
        text = engine_markdown.strip()
    if not text.strip():
        raise RuntimeError("primary markdown output was not written")
    return text.strip()
