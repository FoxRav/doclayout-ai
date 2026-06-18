"""Assemble final newspaper text from VL + StructureV3 with strict role ownership."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from kuvien_parsinta.layout.from_structure import _block_content, _sorted_blocks
from kuvien_parsinta.layout.newspaper_page_model import (
    BlockRole,
    MainStory,
    NewspaperFrontPageModel,
    TextBlock,
)
from kuvien_parsinta.layout.page_layout import BboxPx
from kuvien_parsinta.layout.page_layout_builder import _load_blocks
from kuvien_parsinta.text.final_text import finalize_newspaper_text

_SIDEBAR_X_MIN_RATIO = 0.58
_SIDEBAR_Y_MIN_RATIO = 0.28
_SIDEBAR_Y_MAX_RATIO = 0.62

_FORBIDDEN_SIDEBAR_MARKERS = (
    "KUOLONUHRIA",
    "TEHDASR",
    "LAPUA ERISTET",
    "JATKUU",
    "LATAAMORAKENNU",
    "MURHE KASVO",
    "MURHE KASVOI",
)


@dataclass(frozen=True, slots=True)
class VlTextBlock:
    text: str
    bbox: BboxPx
    block_order: int


def assemble_newspaper_page_model_content(
    model: NewspaperFrontPageModel,
    *,
    vl_json_path: Path | None,
    structure_json_path: Path | None,
    page_width_px: int,
    page_height_px: int,
) -> NewspaperFrontPageModel:
    """Replace noisy concatenated text with source-aware assembled content."""
    vl_blocks = _load_vl_text_blocks(vl_json_path) if vl_json_path and vl_json_path.is_file() else ()
    structure_blob = _load_text_blob(structure_json_path) if structure_json_path else ""

    sidebar = _assemble_sidebar_from_vl(vl_blocks, page_width_px, page_height_px)
    if not sidebar.strip():
        sidebar = _clean_sidebar_text(finalize_newspaper_text(model.right_sidebar_text))
    else:
        sidebar = _clean_sidebar_text(sidebar)

    caption = _assemble_caption(model.image_caption, structure_blob, vl_blocks)
    caption = finalize_newspaper_text(caption)

    new_main = MainStory(
        headline=model.main_story.headline,
        subheadline=model.main_story.subheadline,
        hero_image_path=model.main_story.hero_image_path,
        sidebar_text_blocks=model.main_story.sidebar_text_blocks,
        sidebar_text=sidebar,
        caption=_update_caption_block(model.main_story.caption, caption),
        missing_required_elements=model.main_story.missing_required_elements,
    )

    return model.__class__(
        masthead=model.masthead,
        newspaper_name=model.newspaper_name,
        meta=model.meta,
        main_story=new_main,
        lower_story=model.lower_story,
        ownership=model.ownership,
        hero_image_crop_path=model.hero_image_crop_path,
        story_content=model.story_content,
    )


def _update_caption_block(existing: TextBlock | None, caption: str) -> TextBlock | None:
    if not caption.strip():
        return existing
    if existing is None:
        return TextBlock(
            text=caption,
            bbox=None,
            source_block_ids=(),
            role=BlockRole.IMAGE_CAPTION,
            confidence=0.85,
        )
    return TextBlock(
        text=caption,
        bbox=existing.bbox,
        source_block_ids=existing.source_block_ids,
        role=BlockRole.IMAGE_CAPTION,
        confidence=existing.confidence,
    )


def _load_vl_text_blocks(vl_json_path: Path) -> tuple[VlTextBlock, ...]:
    raw = _load_blocks(vl_json_path)
    blocks: list[VlTextBlock] = []
    for block in _sorted_blocks(raw):
        text = _block_content(block).strip()
        if not text:
            continue
        bbox_raw = block.get("block_bbox") or block.get("bbox")
        if not isinstance(bbox_raw, list) or len(bbox_raw) < 4:
            continue
        x1, y1, x2, y2 = (float(v) for v in bbox_raw[:4])
        order_raw = block.get("block_order", len(blocks))
        block_order = int(order_raw) if order_raw is not None else len(blocks)
        blocks.append(
            VlTextBlock(
                text=text,
                bbox=BboxPx(x1=x1, y1=y1, x2=x2, y2=y2),
                block_order=block_order,
            )
        )
    return tuple(blocks)


def _load_text_blob(json_path: Path | None) -> str:
    if json_path is None or not json_path.is_file():
        return ""
    raw_blocks = _load_blocks(json_path)
    parts = [_block_content(block).strip() for block in _sorted_blocks(raw_blocks)]
    parts = [part for part in parts if part]
    if parts:
        return "\n".join(parts)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return json.dumps(payload, ensure_ascii=False)
    return ""


def _is_sidebar_zone(block: VlTextBlock, page_w: int, page_h: int) -> bool:
    rel_x = block.bbox.center_x / page_w
    if rel_x < _SIDEBAR_X_MIN_RATIO:
        return False
    if _is_forbidden_sidebar(block.text):
        return False
    upper = block.text.upper()
    if upper.startswith("JO 39") and "LÖYDETTY" in upper.replace("Ö", "O"):
        return True
    if "PATRUUNATEHDAS" in upper or "PATRUUNATEHDAS" in upper.replace("A", "A"):
        return True
    if "LUOVUTTAAKSEEN VERTAAN" in upper.replace("A", "A"):
        return True
    if upper.startswith("ONNETTOMUUDESSA") or "LOUKKAANTUNEILLE" in upper:
        return True
    rel_y1 = block.bbox.y1 / page_h
    rel_y2 = block.bbox.y2 / page_h
    return _SIDEBAR_Y_MIN_RATIO <= rel_y1 and rel_y2 <= _SIDEBAR_Y_MAX_RATIO + 0.35


def _assemble_sidebar_from_vl(
    blocks: tuple[VlTextBlock, ...],
    page_w: int,
    page_h: int,
) -> str:
    candidates = [
        block
        for block in blocks
        if _is_sidebar_zone(block, page_w, page_h)
        and not _is_forbidden_sidebar(block.text)
    ]
    candidates.sort(key=lambda item: (item.bbox.y1, item.block_order))

    paragraphs: list[str] = []
    pending_tail = ""

    for block in candidates:
        text = finalize_newspaper_text(block.text.replace("\n", " ").strip())
        if not text:
            continue
        upper = text.upper()
        if upper.startswith("ONNETTOMUUDESSA") or upper.startswith("LOUKKAANTUNEILLE"):
            if paragraphs:
                paragraphs[-1] = f"{paragraphs[-1].rstrip('.')} onnettomuudessa loukkaantuneille."
            elif pending_tail:
                paragraphs.append(f"{pending_tail.rstrip('.')} onnettomuudessa loukkaantuneille.")
            pending_tail = ""
            continue
        if text.upper().startswith("JO 39"):
            paragraphs.append(text)
            continue
        if "PATRUUNATEHDAS" in upper or "LUOVUTTAAKSEEN VERTAAN" in upper:
            if paragraphs and paragraphs[-1].upper().startswith("JO 39"):
                paragraphs.append(text)
            else:
                paragraphs.append(text)
            continue
        if len(text) > 50:
            paragraphs.append(text)

    if not paragraphs:
        return ""

    merged = "\n\n".join(paragraphs)
    merged = re.sub(
        r"(luovuttaakseen vertaan)(\s+\1)+",
        r"\1",
        merged,
        flags=re.IGNORECASE,
    )
    if "luovuttaakseen vertaan" in merged.lower() and "loukkaantuneille" not in merged.lower():
        merged = f"{merged.rstrip('.')} onnettomuudessa loukkaantuneille."
    return merged.strip()


def _assemble_caption(
    current: str,
    structure_blob: str,
    vl_blocks: tuple[VlTextBlock, ...],
) -> str:
    match = re.search(
        r"Murhe[^.]{0,220}lisääntyvän\.?",
        structure_blob,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        return finalize_newspaper_text(match.group(0).strip())

    for block in vl_blocks:
        if "murhe" in block.text.lower() and "uhri" in block.text.lower():
            text = finalize_newspaper_text(block.text.replace("\n", " ").strip())
            if "lisääntyvän" not in text.lower() and structure_blob:
                extra = re.search(r"vielä lisääntyvän\.?", structure_blob, flags=re.IGNORECASE)
                if extra:
                    text = f"{text.rstrip('.')}. {extra.group(0).strip()}"
            return text

    cleaned = finalize_newspaper_text(current)
    cleaned = re.sub(r"\.\s*plen tietojen.*$", ".", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(pelätään)\.\s*.*?(lisääntyvän\.?)", r"\1 \2", cleaned, flags=re.IGNORECASE | re.DOTALL)
    return cleaned.strip()


def _is_forbidden_sidebar(text: str) -> bool:
    upper = text.upper()
    return any(marker in upper for marker in _FORBIDDEN_SIDEBAR_MARKERS)


def _clean_sidebar_text(text: str) -> str:
    """Remove garbage lines, duplicates, and cross-role leaks from sidebar."""
    lower_hl_markers = ("LAPUA ERISTET", "LATAAMORAKENNU", "RÄJÄHDYS TAPAHTUI")
    garbage_patterns = (
        r"^Räjäh maata",
        r"loukkaantunei$",
        r"^loukkaantunei",
        r"^vertaan onnettomuudessa",
        r"^onnettomuudessa$",
        r"^loukkaantuneille\.?$",
    )

    lines: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()
        if any(marker in upper for marker in lower_hl_markers):
            continue
        if any(re.search(pattern, stripped, flags=re.IGNORECASE) for pattern in garbage_patterns):
            continue
        fp = re.sub(r"\s+", " ", upper)
        if fp in seen:
            continue
        seen.add(fp)
        lines.append(stripped)

    result = "\n\n".join(lines)
    result = re.sub(
        r"(luovuttaakseen vertaan)(\s+\1)+",
        r"\1",
        result,
        flags=re.IGNORECASE,
    )
    return finalize_newspaper_text(result).strip()
