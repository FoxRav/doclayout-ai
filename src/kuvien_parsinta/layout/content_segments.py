"""Content segments with strict role ownership for newspaper page model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from kuvien_parsinta.layout.newspaper_page_model import NewspaperFrontPageModel
from kuvien_parsinta.layout.page_layout import BboxPx
from kuvien_parsinta.text.final_text import finalize_newspaper_text


class ContentSegmentRole(str, Enum):
    MASTHEAD = "masthead"
    META = "meta"
    MAIN_HEADLINE = "main_headline"
    SECONDARY_HEADLINE = "secondary_headline"
    MAIN_STORY_SIDEBAR = "main_story_sidebar"
    IMAGE_CAPTION = "image_caption"
    LOWER_HEADLINE = "lower_headline"
    LOWER_STORY_COLUMN = "lower_story_column"
    CONTINUATION = "continuation"


@dataclass(frozen=True, slots=True)
class ContentSegment:
    id: str
    role: ContentSegmentRole
    text: str
    normalized_text: str
    source: str
    bbox: BboxPx | None
    confidence: float
    owner: str
    rendered: bool = False
    render_target: str = ""


def build_content_segments(model: NewspaperFrontPageModel) -> tuple[ContentSegment, ...]:
    """Build ordered content segments from a finalized page model."""
    segments: list[ContentSegment] = []

    def add(
        seg_id: str,
        role: ContentSegmentRole,
        text: str,
        *,
        source: str = "page_model",
        bbox: BboxPx | None = None,
        confidence: float = 0.9,
    ) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        segments.append(
            ContentSegment(
                id=seg_id,
                role=role,
                text=cleaned,
                normalized_text=finalize_newspaper_text(cleaned),
                source=source,
                bbox=bbox,
                confidence=confidence,
                owner=role.value,
                render_target=role.value,
            )
        )

    masthead = f"{model.masthead_text}\n{model.newspaper_name_text}".strip()
    add("masthead", ContentSegmentRole.MASTHEAD, masthead)

    meta_parts = [model.issue_number, model.date_text, model.price_text]
    meta = "\n".join(part for part in meta_parts if part.strip())
    add("meta", ContentSegmentRole.META, meta)

    add("main_headline", ContentSegmentRole.MAIN_HEADLINE, model.main_headline)
    add("secondary_headline", ContentSegmentRole.SECONDARY_HEADLINE, model.secondary_headline)
    add("main_story_sidebar", ContentSegmentRole.MAIN_STORY_SIDEBAR, model.right_sidebar_text)
    add("image_caption", ContentSegmentRole.IMAGE_CAPTION, model.image_caption)
    add("lower_headline", ContentSegmentRole.LOWER_HEADLINE, model.bottom_headline)

    for idx, col in enumerate(model.bottom_column_texts):
        add(f"lower_story_column_{idx}", ContentSegmentRole.LOWER_STORY_COLUMN, col)

    add("continuation", ContentSegmentRole.CONTINUATION, model.continuation_text)
    return tuple(segments)


def detect_content_misassignment(model: NewspaperFrontPageModel) -> list[str]:
    """Return misassignment issues when text appears in wrong role."""
    issues: list[str] = []
    sidebar = model.right_sidebar_text.upper()
    lower_hl = model.bottom_headline.upper()
    lower_body = " ".join(model.bottom_column_texts).upper()

    if lower_hl and lower_hl in sidebar:
        issues.append("lower_headline_in_sidebar")
    if "LATAAMORAKENNU" in sidebar:
        issues.append("lower_story_in_sidebar")
    if "LAPUA ERISTET" in sidebar and lower_hl:
        issues.append("lower_headline_leak_in_sidebar")
    if model.image_caption and model.image_caption[:30] in model.right_sidebar_text:
        issues.append("caption_in_sidebar")

    sidebar_fp = _fingerprint(model.right_sidebar_text)
    for col in model.bottom_column_texts:
        col_fp = _fingerprint(col[:80])
        if col_fp and col_fp in sidebar_fp:
            issues.append("duplicate_sidebar_lower_column")

    if "RÄJÄHDYS TAPAHTUI" in sidebar and "LATAAMORAKENNU" in lower_body:
        issues.append("lower_story_start_in_sidebar")

    return issues


def _fingerprint(text: str) -> str:
    import re

    return re.sub(r"\s+", " ", text.strip().upper())
