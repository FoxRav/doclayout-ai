"""Mojibake repair for OCR output (Finnish-heavy heuristics, safe for other Latin text)."""

from __future__ import annotations

_REPLACEMENT_CHAR = "\ufffd"


def looks_like_mojibake(text: str) -> bool:
    if _REPLACEMENT_CHAR in text:
        return True
    return any(marker in text for marker in ("Ã¤", "Ã¶", "Ã¥", "Â§", "Ã©", "Ã¼"))


def fix_mojibake(text: str) -> str:
    """Best-effort repair of common cp1252/utf-8 confusion. Pure function."""
    if not text or not looks_like_mojibake(text):
        return text
    try:
        recovered = text.encode("cp1252", errors="strict").decode("utf-8", errors="strict")
    except (UnicodeEncodeError, UnicodeDecodeError):
        recovered = text
    return (
        recovered.replace(_REPLACEMENT_CHAR, "")
        .replace("–", "-")
        .replace("—", "-")
    )
