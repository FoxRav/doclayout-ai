"""Shared text layout helpers for PDF renderers."""

from __future__ import annotations

from kuvien_parsinta.layout.page_layout import FontRole


def font_size_for_role(role: FontRole, bbox_height_pt: float) -> float:
    match role:
        case FontRole.MASTHEAD:
            return min(28.0, max(10.0, bbox_height_pt * 0.55))
        case FontRole.HEADLINE:
            return min(36.0, max(12.0, bbox_height_pt * 0.65))
        case FontRole.CAPTION | FontRole.META:
            return min(12.0, max(7.0, bbox_height_pt * 0.45))
        case _:
            return min(11.0, max(7.0, bbox_height_pt * 0.42))


def wrap_text(text: str, *, max_chars: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines
