"""Detect required newspaper story elements (caption, sidebar) from multiple sources."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from kuvien_parsinta.encoding import fix_mojibake
from kuvien_parsinta.layout.from_structure import _block_bbox, _block_content, _sorted_blocks
from kuvien_parsinta.layout.page_layout import BboxPx, LayoutBlock, NewspaperBlockType, PageLayout
from kuvien_parsinta.layout.page_layout_builder import _load_blocks
from kuvien_parsinta.text.ocr_normalization import normalize_ocr_text

CaptionSource = Literal["vl", "structurev3", "opencv", "hybrid", "layout"]

_CAPTION_KEYWORDS = (
    "murhe",
    "uhrien",
    "raunioista",
    "tietojen mukaan",
    "kasvoi",
    "löytyessä",
)
_HEADLINE_MARKERS = ("KUOLONUHRIA", "TEHDASR", "LAPUA ERISTET", "JATKUU")
_METADATA_MARKERS = ("MK (SIS", "N:O ", "PNÄ", "TIISTAINA HUHTIKUUN")


class CaptionSourceKind(str, Enum):
    VL = "vl"
    STRUCTUREV3 = "structurev3"
    OPENCV = "opencv"
    HYBRID = "hybrid"
    LAYOUT = "layout"


@dataclass(frozen=True, slots=True)
class CaptionCandidate:
    text: str
    bbox: BboxPx | None
    source: CaptionSourceKind
    score: float


@dataclass(frozen=True, slots=True)
class StoryContentReport:
    main_story_sidebar_detected: bool
    main_story_sidebar_rendered: bool = False
    image_caption_candidates_count: int = 0
    image_caption_selected: bool = False
    image_caption_rendered: bool = False
    content_loss_detected: bool = False
    missing_required_elements: tuple[str, ...] = ()
    caption_candidates: tuple[CaptionCandidate, ...] = ()

    def to_quality_dict(self) -> dict[str, object]:
        return {
            "main_story_sidebar_detected": self.main_story_sidebar_detected,
            "main_story_sidebar_rendered": self.main_story_sidebar_rendered,
            "image_caption_candidates_count": self.image_caption_candidates_count,
            "image_caption_selected": self.image_caption_selected,
            "image_caption_rendered": self.image_caption_rendered,
            "content_loss_detected": self.content_loss_detected,
            "missing_required_elements": list(self.missing_required_elements),
        }


def hero_bbox_from_layout(layout: PageLayout) -> BboxPx | None:
    hero_blocks = [
        block.bbox_px
        for block in layout.blocks
        if block.block_type is NewspaperBlockType.HERO_IMAGE
    ]
    if not hero_blocks:
        return None
    return max(hero_blocks, key=lambda bbox: bbox.area)


def normalize_caption_text(text: str) -> str:
    cleaned = normalize_ocr_text(text.strip())
    cleaned = re.sub(r"^kuvateksti\s*:?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^[A-Za-zÅÄÖåäö]+\s+(?=Murhe\b)", "", cleaned)
    return cleaned.strip()


def looks_like_caption_text(text: str) -> bool:
    cleaned = normalize_caption_text(text)
    if len(cleaned) < 25:
        return False
    lower = cleaned.lower()
    if any(marker in cleaned.upper() for marker in _HEADLINE_MARKERS):
        return False
    if any(marker in cleaned.upper() for marker in _METADATA_MARKERS):
        return False
    keyword_hits = sum(1 for keyword in _CAPTION_KEYWORDS if keyword in lower)
    if keyword_hits >= 2:
        return True
    if "murhe" in lower and "uhri" in lower:
        return True
    return False


def detect_sidebar_source_candidate(
    blocks: tuple[LayoutBlock, ...],
    *,
    page_w: float,
    page_h: float,
) -> bool:
    for block in blocks:
        if not block.text.strip():
            continue
        rel_x = block.bbox_px.center_x / page_w
        rel_y = block.bbox_px.center_y / page_h
        if rel_x < 0.62 or rel_y < 0.34 or rel_y > 0.78:
            continue
        upper = block.text.upper()
        if upper.startswith("JO 39") or "LÖYDETTY KUOLE" in upper:
            return True
        if block.block_type is NewspaperBlockType.RIGHT_SIDEBAR and len(block.text) >= 40:
            return True
    return False


def score_caption_candidate(
    text: str,
    bbox: BboxPx | None,
    *,
    hero_bbox: BboxPx | None,
    page_w: float,
    page_h: float,
) -> float:
    cleaned = normalize_caption_text(text)
    if not cleaned:
        return -10.0

    score = 0.0
    lower = cleaned.lower()
    upper = cleaned.upper()

    if hero_bbox is not None and bbox is not None:
        if bbox.y1 >= hero_bbox.y2 - page_h * 0.02:
            score += 3.0
        if hero_bbox.width > 0:
            width_ratio = bbox.width / hero_bbox.width
            if 0.45 <= width_ratio <= 1.6:
                score += 2.0
        rel_y = bbox.center_y / page_h
        if rel_y > 0.62:
            score -= 5.0
        if bbox.height / page_h < 0.05:
            score += 2.0

    for keyword in _CAPTION_KEYWORDS:
        if keyword in lower:
            score += 2.0

    if any(marker in upper for marker in _HEADLINE_MARKERS):
        score -= 5.0
    if any(marker in upper for marker in _METADATA_MARKERS):
        score -= 5.0
    if len(cleaned) > 220:
        score -= 2.0
    return score


def find_caption_candidates(
    *,
    blocks: tuple[LayoutBlock, ...],
    layout: PageLayout,
    vl_json_path: Path | None,
    structure_json_path: Path | None,
    hero_bbox: BboxPx | None,
) -> list[CaptionCandidate]:
    page_w = float(layout.page_width_px)
    page_h = float(layout.page_height_px)
    candidates: list[CaptionCandidate] = []

    for block in blocks:
        if not block.text.strip():
            continue
        if block.block_type is NewspaperBlockType.IMAGE_CAPTION:
            text = normalize_caption_text(block.text)
            if text:
                candidates.append(
                    _make_candidate(
                        text=text,
                        bbox=block.bbox_px,
                        source=CaptionSourceKind.LAYOUT,
                        hero_bbox=hero_bbox,
                        page_w=page_w,
                        page_h=page_h,
                    )
                )
            continue
        if not looks_like_caption_text(block.text):
            continue
        rel_y = block.bbox_px.center_y / page_h
        if hero_bbox is not None:
            if block.bbox_px.y1 < hero_bbox.y2 - page_h * 0.03:
                continue
        elif rel_y < 0.45 or rel_y > 0.72:
            continue
        candidates.append(
            _make_candidate(
                text=normalize_caption_text(block.text),
                bbox=block.bbox_px,
                source=CaptionSourceKind.LAYOUT,
                hero_bbox=hero_bbox,
                page_w=page_w,
                page_h=page_h,
            )
        )

    for json_path, source in (
        (vl_json_path, CaptionSourceKind.VL),
        (structure_json_path, CaptionSourceKind.STRUCTUREV3),
    ):
        candidates.extend(
            _candidates_from_engine_json(
                json_path=json_path,
                source=source,
                hero_bbox=hero_bbox,
                page_w=page_w,
                page_h=page_h,
            )
        )

    candidates.extend(
        _candidates_from_geometry(
            blocks=blocks,
            hero_bbox=hero_bbox,
            page_w=page_w,
            page_h=page_h,
        )
    )

    return _dedupe_candidates(candidates)


def select_best_caption(candidates: list[CaptionCandidate]) -> CaptionCandidate | None:
    if not candidates:
        return None
    ranked = sorted(candidates, key=lambda item: item.score, reverse=True)
    best = ranked[0]
    if best.score < 1.0:
        return None
    return best


def build_story_content_report(
    *,
    sidebar_text: str,
    caption_text: str,
    caption_candidates: tuple[CaptionCandidate, ...],
    sidebar_source_detected: bool,
) -> StoryContentReport:
    missing: list[str] = []
    caption_selected = bool(caption_text.strip())
    sidebar_detected = bool(sidebar_text.strip()) or sidebar_source_detected

    if sidebar_source_detected and not sidebar_text.strip():
        missing.append("main_story.sidebar_text")
    if caption_candidates and not caption_selected:
        missing.append("main_story.caption")

    content_loss = bool(missing)
    return StoryContentReport(
        main_story_sidebar_detected=sidebar_detected,
        image_caption_candidates_count=len(caption_candidates),
        image_caption_selected=caption_selected,
        content_loss_detected=content_loss,
        missing_required_elements=tuple(missing),
        caption_candidates=caption_candidates,
    )


def _make_candidate(
    *,
    text: str,
    bbox: BboxPx | None,
    source: CaptionSourceKind,
    hero_bbox: BboxPx | None,
    page_w: float,
    page_h: float,
) -> CaptionCandidate:
    score = score_caption_candidate(
        text,
        bbox,
        hero_bbox=hero_bbox,
        page_w=page_w,
        page_h=page_h,
    )
    return CaptionCandidate(text=text, bbox=bbox, source=source, score=score)


def _candidates_from_engine_json(
    *,
    json_path: Path | None,
    source: CaptionSourceKind,
    hero_bbox: BboxPx | None,
    page_w: float,
    page_h: float,
) -> list[CaptionCandidate]:
    if json_path is None or not json_path.is_file():
        return []

    raw_blocks = _load_blocks(json_path)
    found: list[CaptionCandidate] = []
    for block in _sorted_blocks(raw_blocks):
        text = fix_mojibake(_block_content(block).strip())
        if not looks_like_caption_text(text):
            continue
        bbox_raw = _block_bbox(block)
        bbox = (
            BboxPx(float(bbox_raw[0]), float(bbox_raw[1]), float(bbox_raw[2]), float(bbox_raw[3]))
            if bbox_raw is not None
            else None
        )
        if hero_bbox is not None and bbox is not None and bbox.y1 < hero_bbox.y2 - page_h * 0.03:
            continue
        found.append(
            _make_candidate(
                text=normalize_caption_text(text),
                bbox=bbox,
                source=source,
                hero_bbox=hero_bbox,
                page_w=page_w,
                page_h=page_h,
            )
        )
    return found


def _candidates_from_geometry(
    *,
    blocks: tuple[LayoutBlock, ...],
    hero_bbox: BboxPx | None,
    page_w: float,
    page_h: float,
) -> list[CaptionCandidate]:
    if hero_bbox is None:
        return []

    lower_y = hero_bbox.y2 + page_h * 0.005
    upper_y = hero_bbox.y2 + page_h * 0.12
    found: list[CaptionCandidate] = []
    for block in blocks:
        if not block.text.strip():
            continue
        bbox = block.bbox_px
        if bbox.y1 < lower_y or bbox.y1 > upper_y:
            continue
        if bbox.x2 < hero_bbox.x1 - page_w * 0.02:
            continue
        if bbox.width > hero_bbox.width * 1.25:
            continue
        if not looks_like_caption_text(block.text):
            continue
        found.append(
            _make_candidate(
                text=normalize_caption_text(block.text),
                bbox=bbox,
                source=CaptionSourceKind.OPENCV,
                hero_bbox=hero_bbox,
                page_w=page_w,
                page_h=page_h,
            )
        )
    return found


def _dedupe_candidates(candidates: list[CaptionCandidate]) -> list[CaptionCandidate]:
    kept: list[CaptionCandidate] = []
    for candidate in candidates:
        if not candidate.text.strip():
            continue
        norm = re.sub(r"\s+", " ", candidate.text.lower())
        if any(
            norm[:40] in re.sub(r"\s+", " ", existing.text.lower())[:80]
            or re.sub(r"\s+", " ", existing.text.lower())[:40] in norm[:80]
            for existing in kept
        ):
            for idx, existing in enumerate(kept):
                if norm[:30] == re.sub(r"\s+", " ", existing.text.lower())[:30]:
                    if candidate.score > existing.score:
                        kept[idx] = candidate
                    break
            continue
        kept.append(candidate)
    return kept
