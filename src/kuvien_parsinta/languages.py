"""Multilingual OCR language selection."""

from __future__ import annotations

from enum import Enum


class OcrLanguageMode(str, Enum):
    """How OCR language is chosen per document."""

    AUTO = "auto"
    EXPLICIT = "explicit"


# PaddleOCR / PP-OCR language codes we support out of the box.
# Primary Finnish; extend by adding codes documented in PaddleOCR lang list.
PRIMARY_LANGUAGE: str = "fi"

DEFAULT_LANGUAGE_PRIORITY: tuple[str, ...] = ("fi", "sv", "en")

# Common European + Latin script fallback when auto-detect is inconclusive.
LATIN_FALLBACK: str = "latin"


def normalize_lang_code(code: str) -> str:
    """Lowercase ISO-like code used by PaddleOCR."""
    return code.strip().lower().replace("_", "-").split("-")[0]


def merge_language_priority(
    *,
    primary: str,
    extra: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Build deduplicated priority list with primary first."""
    seen: set[str] = set()
    ordered: list[str] = []
    for code in (normalize_lang_code(primary), *(normalize_lang_code(c) for c in extra)):
        if code and code not in seen:
            seen.add(code)
            ordered.append(code)
    return tuple(ordered)


def paddle_lang_for_attempt(
    *,
    attempt_index: int,
    priority: tuple[str, ...],
) -> str:
    """Return PaddleOCR lang argument for a given fallback attempt."""
    if attempt_index < len(priority):
        return priority[attempt_index]
    return LATIN_FALLBACK


def structure_lang_for_paddle(code: str) -> str:
    """Map app language codes to PP-StructureV3-supported PaddleOCR langs."""
    normalized = normalize_lang_code(code)
    if normalized == "fi":
        return "sv"
    supported = {
        "en",
        "sv",
        "de",
        "fr",
        "es",
        "it",
        "nl",
        "pl",
        "pt",
        "da",
        "no",
        "cs",
        "hu",
        "ro",
        "tr",
        "vi",
        "id",
        "ch",
    }
    if normalized in supported:
        return normalized
    return "sv"
