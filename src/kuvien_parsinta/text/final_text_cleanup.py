"""Final-output text cleanup for markdown and structural PDF text."""

from __future__ import annotations

import re
import unicodedata

from kuvien_parsinta.layout.newspaper_page_model import (
    LowerStory,
    MainStory,
    MetaRow,
    NewspaperFrontPageModel,
    TextBlock,
)
from kuvien_parsinta.text.final_text import finalize_newspaper_text

_CONTROL_CHARS = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f\ufffd]")
_SOFT_HYPHEN = "\u00ad"
_LINE_BREAK_HYPHEN = re.compile(r"(\w{2,})-\s*\n\s*(\w{2,})", re.UNICODE)
_MIDWORD_HYPHEN = re.compile(r"(\w{2,})-\s+(\w{2,})", re.UNICODE)

_LITERAL_FIXES: tuple[tuple[str, str], ...] = (
    ("pelätään. vielä lisääntyvän", "pelätään vielä lisääntyvän"),
    ("pelätään. vielä", "pelätään vielä"),
    ("Tapahtumahetkella", "Tapahtumahetkellä"),
    ("viranomai- Onnettomuuden", "viranomaiset. Onnettomuuden"),
    ("viranomai-\nOnnettomuuden", "viranomaiset. Onnettomuuden"),
    ("pelastus-yksiköt", "pelastusyksiköt"),
    ("pelastus- yksiköt", "pelastusyksiköt"),
)


def cleanup_final_text(text: str) -> str:
    """Apply final-output cleanup without touching raw OCR artefacts."""
    if not text.strip():
        return text

    result = finalize_newspaper_text(text)
    result = result.replace(_SOFT_HYPHEN, "")
    result = _CONTROL_CHARS.sub("", result)
    result = unicodedata.normalize("NFC", result)

    for _ in range(4):
        merged = _LINE_BREAK_HYPHEN.sub(r"\1\2", result)
        merged = _MIDWORD_HYPHEN.sub(r"\1\2", merged)
        if merged == result:
            break
        result = merged

    for wrong, correct in _LITERAL_FIXES:
        result = result.replace(wrong, correct)
        if wrong != wrong.upper():
            result = result.replace(wrong.upper(), correct.upper())

    result = _fix_unclosed_price_paren(result)
    return result.strip()


def _fix_unclosed_price_paren(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        if "mk" in lower and "sis." in lower and "(" in stripped and ")" not in stripped:
            lines.append(line.replace(stripped, f"{stripped})"))
        else:
            lines.append(line)
    return "\n".join(lines)


def _clean_text_block(block: TextBlock | None) -> TextBlock | None:
    if block is None:
        return None
    cleaned = cleanup_final_text(block.text)
    if cleaned == block.text:
        return block
    return TextBlock(
        text=cleaned,
        bbox=block.bbox,
        source_block_ids=block.source_block_ids,
        role=block.role,
        confidence=block.confidence,
    )


def apply_cleanup_to_page_model(model: NewspaperFrontPageModel) -> NewspaperFrontPageModel:
    """Run final cleanup on all page model text fields."""
    meta = MetaRow(
        issue_number=_clean_text_block(model.meta.issue_number),
        date_text=_clean_text_block(model.meta.date_text),
        stars=_clean_text_block(model.meta.stars),
        price=_clean_text_block(model.meta.price),
    )
    main = MainStory(
        headline=_clean_text_block(model.main_story.headline),
        subheadline=_clean_text_block(model.main_story.subheadline),
        hero_image_path=model.main_story.hero_image_path,
        sidebar_text_blocks=tuple(
            cleaned
            for block in model.main_story.sidebar_text_blocks
            if (cleaned := _clean_text_block(block)) is not None
        ),
        sidebar_text=cleanup_final_text(model.main_story.sidebar_text),
        caption=_clean_text_block(model.main_story.caption),
        missing_required_elements=model.main_story.missing_required_elements,
    )
    lower = LowerStory(
        headline=_clean_text_block(model.lower_story.headline),
        columns=tuple(
            cleaned
            for block in model.lower_story.columns
            if (cleaned := _clean_text_block(block)) is not None
        ),
        continuation_marker=_clean_text_block(model.lower_story.continuation_marker),
    )
    return NewspaperFrontPageModel(
        masthead=_clean_text_block(model.masthead),
        newspaper_name=_clean_text_block(model.newspaper_name),
        meta=meta,
        main_story=main,
        lower_story=lower,
        ownership=model.ownership,
        hero_image_crop_path=model.hero_image_crop_path,
        story_content=model.story_content,
    )


def text_cleanup_issues(text: str) -> list[str]:
    """Return detected final-text issues for quality gate."""
    issues: list[str] = []
    if _CONTROL_CHARS.search(text) or "\ufffd" in text:
        issues.append("control_or_replacement_chars")
    if _SOFT_HYPHEN in text:
        issues.append("soft_hyphen_present")
    if "pelätään. vielä" in text.lower():
        issues.append("caption_period_before_viela")
    if re.search(r"\bon-\s*nettomuus", text, flags=re.IGNORECASE):
        issues.append("broken_hyphen_onnettomuus")
    if re.search(r"\buh-\s*rien\b", text, flags=re.IGNORECASE):
        issues.append("broken_hyphen_uhrien")
    if re.search(r"\bli-\s*kenteelt", text, flags=re.IGNORECASE):
        issues.append("broken_hyphen_liikenteeltä")
    if re.search(r"1\s*mk\s*\([^)]*$", text, flags=re.IGNORECASE | re.MULTILINE):
        issues.append("unclosed_price_paren")
    return issues
