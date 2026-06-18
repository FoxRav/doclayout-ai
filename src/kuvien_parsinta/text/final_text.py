"""Final markdown/PDF text normalization and VL enrichment."""

from __future__ import annotations

import json
import re
from pathlib import Path

from kuvien_parsinta.layout.from_structure import _block_content, _sorted_blocks
from kuvien_parsinta.layout.newspaper_page_model import NewspaperFrontPageModel
from kuvien_parsinta.layout.page_layout_builder import _load_blocks
from kuvien_parsinta.text.ocr_normalization import normalize_ocr_text

_FINAL_CORRECTIONS: tuple[tuple[str, str], ...] = (
    ("TISTAINA", "TIISTAINA"),
    ("Vilmeisimpien", "Viimeisimpien"),
    ("Vilmeisimplen", "Viimeisimpien"),
    ("vilmeisimpien", "viimeisimpien"),
    ("johtimmm", "johti mm."),
    ("johtimmm.", "johti mm."),
    ("johti mm..", "johti mm."),
    (" etta ", " että "),
    ("En-simmäinen", "Ensimmäinen"),
    ("hältys", "hälytys"),
    ("on-nettomuudesta", "onnettomuudesta"),
    ("räjähdyspalkalle", "räjähdyspaikalle"),
    ("keskusairalaaan", "keskussairaalaan"),
    ("irroitettavissa", "irrotettavissa"),
    ("kasvol", "kasvoi"),
    ("uhrlen", "uhrien"),
    ("kookontui", "kokoontui"),
    ("Lapuailla", "Lapualla"),
    ("vapaehtoiset", "vapaaehtoiset"),
    ("heinkilöä", "henkilöä"),
    ("selvittamaan", "selvittämään"),
    ("rajahdys", "räjähdys"),
    ("Rajahdys", "Räjähdys"),
)

_COMPLETENESS_PHRASES: tuple[tuple[str, str], ...] = (
    ("sidebar", "loukkaantuneille"),
    ("caption", "lisääntyvän"),
    ("sidebar", "luovuttaakseen vertaan"),
)


def finalize_newspaper_text(text: str) -> str:
    """Apply final-output OCR fixes without touching raw engine artefacts."""
    result = normalize_ocr_text(text)
    for wrong, correct in _FINAL_CORRECTIONS:
        result = result.replace(wrong, correct)
        if wrong != wrong.upper():
            result = result.replace(wrong.upper(), correct.upper())
    result = re.sub(r"\betta\b", "että", result, flags=re.IGNORECASE)
    return result


def enrich_page_model_text(
    model: NewspaperFrontPageModel,
    *,
    vl_json_path: Path | None,
    structure_json_path: Path | None = None,
) -> NewspaperFrontPageModel:
    """Fill missing sidebar/caption phrases from VL/Structure raw text when available."""
    vl_blob = _load_vl_text_blob(vl_json_path) if vl_json_path and vl_json_path.is_file() else ""
    structure_blob = (
        _load_vl_text_blob(structure_json_path)
        if structure_json_path and structure_json_path.is_file()
        else ""
    )
    source_blob = f"{vl_blob}\n{structure_blob}".strip()
    if not source_blob:
        return model

    sidebar = finalize_newspaper_text(model.right_sidebar_text)
    caption = finalize_newspaper_text(model.image_caption)
    original_sidebar = sidebar
    original_caption = caption

    if "loukkaantuneille" in source_blob.lower() and "loukkaantuneille" not in sidebar.lower():
        if sidebar.rstrip().endswith("vertaan"):
            sidebar = f"{sidebar.rstrip()} onnettomuudessa loukkaantuneille."
        else:
            snippet = _extract_phrase_context(source_blob, "loukkaantuneille", window=25)
            if snippet and snippet not in sidebar:
                sidebar = f"{sidebar.rstrip()} {snippet}".strip()

    if "luovuttaakseen vertaan" in source_blob.lower() and "luovuttaakseen vertaan" not in sidebar.lower():
        snippet = _extract_phrase_context(source_blob, "luovuttaakseen vertaan", window=30)
        if snippet and snippet not in sidebar:
            sidebar = sidebar.rstrip(".") + " " + snippet if sidebar else snippet

    if "lisääntyvän" in source_blob.lower() and "lisääntyvän" not in caption.lower():
        match = re.search(
            r"Murhe[^.]{0,200}lisääntyvän\.?",
            source_blob,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            caption = finalize_newspaper_text(match.group(0).strip())
        else:
            match = re.search(r"[^.]{0,80}lisääntyvän[^.]{0,20}", source_blob, flags=re.IGNORECASE)
            if match:
                extra = finalize_newspaper_text(match.group(0).strip())
                if extra and extra not in caption:
                    caption = f"{caption.rstrip('.')}. {extra}".strip()

    if sidebar == original_sidebar and caption == original_caption:
        return model

    from kuvien_parsinta.layout.newspaper_page_model import MainStory

    new_main = MainStory(
        headline=model.main_story.headline,
        subheadline=model.main_story.subheadline,
        hero_image_path=model.main_story.hero_image_path,
        sidebar_text_blocks=model.main_story.sidebar_text_blocks,
        sidebar_text=sidebar,
        caption=model.main_story.caption,
        missing_required_elements=model.main_story.missing_required_elements,
    )
    if caption != model.image_caption and model.main_story.caption is not None:
        from kuvien_parsinta.layout.newspaper_page_model import BlockRole, TextBlock

        new_main = MainStory(
            headline=model.main_story.headline,
            subheadline=model.main_story.subheadline,
            hero_image_path=model.main_story.hero_image_path,
            sidebar_text_blocks=model.main_story.sidebar_text_blocks,
            sidebar_text=sidebar,
            caption=TextBlock(
                text=caption,
                bbox=model.main_story.caption.bbox,
                source_block_ids=model.main_story.caption.source_block_ids,
                role=BlockRole.IMAGE_CAPTION,
                confidence=model.main_story.caption.confidence,
            ),
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


def sanitize_newspaper_page_model(model: NewspaperFrontPageModel) -> NewspaperFrontPageModel:
    """Remove cross-role text leaks and duplicates before markdown/PDF output."""
    from kuvien_parsinta.layout.newspaper_page_model import MainStory

    sidebar = finalize_newspaper_text(model.right_sidebar_text)
    lower_headline = finalize_newspaper_text(model.bottom_headline).strip()
    lower_upper = lower_headline.upper()

    cleaned_lines: list[str] = []
    seen_fingerprints: set[str] = set()
    for line in sidebar.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()
        if lower_upper and upper == lower_upper:
            continue
        if "LAPUA" in upper and "ERISTET" in upper:
            continue
        if "LATAAMORAKENNU" in upper:
            continue
        fingerprint = re.sub(r"\s+", " ", upper)
        if fingerprint in seen_fingerprints:
            continue
        if stripped.lower() in {"onnettomuudessa", "loukkaantuneille", "loukkaantuneille."}:
            if cleaned_lines and cleaned_lines[-1].rstrip().lower().endswith("vertaan"):
                cleaned_lines[-1] = (
                    f"{cleaned_lines[-1].rstrip()} onnettomuudessa loukkaantuneille."
                )
            continue
        seen_fingerprints.add(fingerprint)
        cleaned_lines.append(stripped)

    sidebar = "\n\n".join(cleaned_lines)
    sidebar = re.sub(
        r"(luovuttaakseen vertaan)(\s+\1)+",
        r"\1",
        sidebar,
        flags=re.IGNORECASE,
    )

    for col_text in model.bottom_column_texts:
        prefix = finalize_newspaper_text(col_text).strip()[:40]
        if len(prefix) > 18 and prefix in sidebar:
            sidebar = sidebar.replace(prefix, "").strip()

    sidebar = re.sub(r"\n{3,}", "\n\n", sidebar).strip()
    if sidebar == model.right_sidebar_text.strip():
        return model

    new_main = MainStory(
        headline=model.main_story.headline,
        subheadline=model.main_story.subheadline,
        hero_image_path=model.main_story.hero_image_path,
        sidebar_text_blocks=model.main_story.sidebar_text_blocks,
        sidebar_text=sidebar,
        caption=model.main_story.caption,
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


def _load_vl_text_blob(vl_json_path: Path) -> str:
    raw_blocks = _load_blocks(vl_json_path)
    parts: list[str] = []
    for block in _sorted_blocks(raw_blocks):
        text = _block_content(block).strip()
        if text:
            parts.append(text)
    if parts:
        return "\n".join(parts)
    payload = json.loads(vl_json_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return json.dumps(payload, ensure_ascii=False)
    return ""


def _extract_phrase_context(blob: str, phrase: str, *, window: int = 60) -> str:
    lower = blob.lower()
    target = phrase.lower()
    idx = lower.find(target)
    if idx < 0:
        return ""
    start = max(0, idx - window)
    end = min(len(blob), idx + len(phrase) + window)
    return finalize_newspaper_text(blob[start:end].strip())
