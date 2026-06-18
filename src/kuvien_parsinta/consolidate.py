"""Merge per-page OCR JSON into consolidated markdown."""

from __future__ import annotations

import json
from pathlib import Path

from kuvien_parsinta.encoding import fix_mojibake


def _page_text_from_json(res_json_path: Path) -> str | None:
    try:
        data = json.loads(res_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    res = data.get("res") if isinstance(data, dict) else None
    payload = res if isinstance(res, dict) else data
    if not isinstance(payload, dict):
        return None
    parsing = payload.get("parsing_res_list")
    if isinstance(parsing, list) and parsing:
        blocks = []
        for block in parsing:
            if not isinstance(block, dict):
                continue
            label = block.get("block_label", "")
            if label in {"header", "footer", "number", "footnote", "image", "figure"}:
                continue
            content = block.get("block_content", "")
            if isinstance(content, str) and content.strip():
                blocks.append(content.strip())
        joined = "\n\n".join(blocks).strip()
        if joined:
            return fix_mojibake(joined)
    ocr = payload.get("overall_ocr_res", {})
    texts = ocr.get("rec_texts") if isinstance(ocr, dict) else None
    if isinstance(texts, list) and texts:
        return fix_mojibake("\n".join(str(t) for t in texts).strip())
    return None


def consolidate_pages(
    *,
    pages_dir: Path,
    page_count: int,
    out_path: Path,
    *,
    include_page_markers: bool = True,
) -> Path:
    """Write structural markdown from page artefacts."""
    lines: list[str] = []
    for page_no in range(page_count):
        json_path = pages_dir / f"{page_no:03d}.res.json"
        md_path = pages_dir / f"{page_no:03d}.md"
        text = _page_text_from_json(json_path)
        if text is None and md_path.exists():
            text = fix_mojibake(md_path.read_text(encoding="utf-8", errors="replace"))
        if text is None:
            continue
        if include_page_markers:
            lines.append(f"\n\n<!-- page: {page_no} -->\n\n")
        lines.append(text)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(lines).strip() + "\n", encoding="utf-8")
    return out_path
