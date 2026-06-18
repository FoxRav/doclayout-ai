"""Reflow OCR lines into readable flowing markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from kuvien_parsinta.encoding import fix_mojibake


@dataclass(frozen=True, slots=True)
class LayoutLine:
    text: str
    y_min: float
    y_max: float
    x_min: float
    x_max: float

    @property
    def width(self) -> float:
        return self.x_max - self.x_min


def poly_bbox(poly: Sequence[Sequence[float]]) -> tuple[float, float, float, float]:
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def layout_lines_from_ocr(
    texts: Sequence[str],
    polys: Sequence[Sequence[Sequence[float]]] | None,
) -> list[LayoutLine]:
    """Pair OCR texts with bounding boxes; synthesize vertical order if polys missing."""
    lines: list[LayoutLine] = []
    for idx, text in enumerate(texts):
        if polys and idx < len(polys):
            x_min, y_min, x_max, y_max = poly_bbox(polys[idx])
        else:
            x_min, y_min, x_max, y_max = 0.0, float(idx), 100.0, float(idx) + 1.0
        lines.append(
            LayoutLine(
                text=str(text),
                y_min=y_min,
                y_max=y_max,
                x_min=x_min,
                x_max=x_max,
            )
        )
    return sorted(lines, key=lambda line: (line.y_min, line.x_min))


def dehyphenate_lines(lines: Sequence[LayoutLine]) -> list[LayoutLine]:
    merged = list(lines)
    while True:
        changed = False
        next_pass: list[LayoutLine] = []
        idx = 0
        while idx < len(merged):
            current = merged[idx]
            text = current.text.rstrip()
            if text.endswith("-") and idx + 1 < len(merged):
                nxt = merged[idx + 1]
                next_pass.append(
                    LayoutLine(
                        text=text[:-1] + nxt.text.lstrip(),
                        y_min=min(current.y_min, nxt.y_min),
                        y_max=max(current.y_max, nxt.y_max),
                        x_min=min(current.x_min, nxt.x_min),
                        x_max=max(current.x_max, nxt.x_max),
                    )
                )
                idx += 2
                changed = True
                continue
            next_pass.append(current)
            idx += 1
        merged = next_pass
        if not changed:
            return merged


def _median_line_height(lines: Sequence[LayoutLine]) -> float:
    heights = [max(1.0, line.y_max - line.y_min) for line in lines]
    heights.sort()
    return heights[len(heights) // 2]


def group_body_paragraphs(lines: Sequence[LayoutLine]) -> list[str]:
    if not lines:
        return []
    gap_threshold = _median_line_height(lines) * 1.25
    paragraphs: list[list[str]] = [[lines[0].text.strip()]]
    for prev, curr in zip(lines, lines[1:], strict=False):
        gap = curr.y_min - prev.y_max
        if gap > gap_threshold:
            paragraphs.append([curr.text.strip()])
        else:
            paragraphs[-1].append(curr.text.strip())
    return [" ".join(part for part in group if part) for group in paragraphs if group]


def is_probable_signature(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 3 or not stripped.endswith("."):
        return False
    letters = [char for char in stripped if char.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
    return upper_ratio >= 0.85


_HEADLINE_HEIGHT_RATIO = 2.0
_MASTHEAD_RE = re.compile(
    r"UUTISLEHTI|tuotantoa valvoo|jatkuvasti VTT|Milta- ja hinta|"
    r"Tampella|Metsäteollisuus|Porvoo|Puh\.\s*\d|06101",
    re.IGNORECASE,
)

_DATELINE_RE = re.compile(
    r"(päivän|päiväl|päivänä|päivä|tammikuun|helmikuun|maaliskuun|huhtikuun|"
    r"toukokuun|kesäkuun|heinäkuun|elokuun|syyskuun|lokakuun|marraskuun|joulukuun)",
    re.IGNORECASE,
)


def _line_height(line: LayoutLine) -> float:
    return max(1.0, line.y_max - line.y_min)


def _is_masthead(text: str) -> bool:
    return bool(_MASTHEAD_RE.search(text))


def _find_headline_indices(lines: Sequence[LayoutLine]) -> list[int]:
    if not lines:
        return []
    median_h = _median_line_height(lines)
    threshold = median_h * _HEADLINE_HEIGHT_RATIO
    candidates = [
        idx
        for idx, line in enumerate(lines)
        if _line_height(line) >= threshold and not _is_masthead(line.text)
    ]
    if not candidates:
        return []

    runs: list[list[int]] = []
    current = [candidates[0]]
    for idx in candidates[1:]:
        prev = lines[current[-1]]
        curr = lines[idx]
        gap = curr.y_min - prev.y_max
        if gap <= median_h * 2.5:
            current.append(idx)
        else:
            runs.append(current)
            current = [idx]
    runs.append(current)
    return max(runs, key=lambda run: sum(_line_height(lines[i]) for i in run))


def _join_headline_text(lines: Sequence[LayoutLine]) -> str:
    merged = dehyphenate_lines(list(lines))
    return " ".join(line.text.strip() for line in merged if line.text.strip())


def _fallback_title(lines: Sequence[LayoutLine]) -> tuple[str, list[LayoutLine]]:
    merged = dehyphenate_lines(list(lines))
    if not merged:
        return "Asiakirja", []
    first = merged[0].text.strip()
    if len(first) > 120:
        first = first[:117].rstrip() + "..."
    if len(first) < 10 and len(merged) > 1:
        combined = f"{first} {merged[1].text.strip()}".strip()
        first = combined[:120].rstrip()
        return first, merged[2:]
    return first or "Asiakirja", merged[1:]


def extract_title(lines: Sequence[LayoutLine]) -> tuple[str, list[LayoutLine]]:
    """Detect headline from layout; never use the input filename."""
    ordered = list(lines)
    headline_indices = _find_headline_indices(ordered)
    if headline_indices:
        headline_lines = [ordered[idx] for idx in headline_indices]
        remaining = [line for idx, line in enumerate(ordered) if idx not in headline_indices]
        return _join_headline_text(headline_lines), remaining
    return _fallback_title(ordered)


def is_probable_dateline(text: str) -> bool:
    stripped = text.strip()
    if not stripped or is_probable_signature(stripped):
        return False
    has_year = bool(re.search(r"\b(18|19|20)\d{2}\b", stripped))
    has_place = "," in stripped
    return has_year and (has_place or bool(_DATELINE_RE.search(stripped)))


def split_trailing_blocks(lines: list[LayoutLine]) -> tuple[list[LayoutLine], str | None, str | None]:
    """Pull signature and dateline off the end when heuristics match."""
    signature: str | None = None
    dateline: str | None = None
    remaining = list(lines)

    if remaining and is_probable_signature(remaining[-1].text):
        signature = remaining.pop().text.strip()

    if len(remaining) >= 2 and not is_probable_dateline(remaining[-1].text):
        maybe = f"{remaining[-2].text.strip()} {remaining[-1].text.strip()}".strip()
        if is_probable_dateline(maybe):
            dateline = maybe
            remaining = remaining[:-2]
    elif remaining and is_probable_dateline(remaining[-1].text):
        dateline = remaining.pop().text.strip()

    return remaining, dateline, signature


def flowing_text_from_lines(lines: Sequence[LayoutLine]) -> tuple[list[str], str | None, str | None]:
    merged = dehyphenate_lines(list(lines))
    body_lines, dateline, signature = split_trailing_blocks(merged)
    return group_body_paragraphs(body_lines), dateline, signature


def format_flowing_markdown(
    *,
    title: str,
    body_paragraphs: Sequence[str],
    dateline: str | None = None,
    signature: str | None = None,
) -> str:
    parts: list[str] = [f"# {title.strip()}", ""]
    for paragraph in body_paragraphs:
        cleaned = paragraph.strip()
        if cleaned:
            parts.extend((cleaned, ""))
    if dateline:
        parts.extend((dateline.strip(), ""))
    if signature:
        parts.extend((f"**{signature.strip()}**", ""))
    return "\n".join(parts).rstrip() + "\n"


def ocr_to_flowing_markdown(
    *,
    texts: Sequence[str],
    polys: Sequence[Sequence[Sequence[float]]] | None,
    title: str | None = None,
) -> str:
    lines = layout_lines_from_ocr(texts, polys)
    resolved_title, body_lines = (
        (title, lines) if title is not None else extract_title(lines)
    )
    body, dateline, signature = flowing_text_from_lines(body_lines)
    return fix_mojibake(
        format_flowing_markdown(
            title=resolved_title,
            body_paragraphs=body,
            dateline=dateline,
            signature=signature,
        )
    )
