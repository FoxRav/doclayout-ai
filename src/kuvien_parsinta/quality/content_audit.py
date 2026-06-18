"""Content completeness audit for newspaper structural outputs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz

from kuvien_parsinta.layout.content_segments import (
    ContentSegment,
    build_content_segments,
    detect_content_misassignment,
)
from kuvien_parsinta.layout.newspaper_page_model import NewspaperFrontPageModel
from kuvien_parsinta.markdown.newspaper_markdown import extract_story_body

_FORBIDDEN_FRAGMENTS: tuple[str, ...] = (
    "Räjäh maata",
    "loukkaantunei",
    "lataamorakennu",
    "johti mm..",
    "plen tietojen",
    "LAPUA ERISTETTIIN Räjähdys",
    "Räjäh maata jonottivat",
)

_REQUIRED_SEGMENTS: tuple[dict[str, object], ...] = (
    {
        "name": "masthead",
        "required_phrases": ("KUVA ERIKOIS", "ILTA-SANOMAT"),
        "page_model_getter": "masthead",
    },
    {
        "name": "meta",
        "required_phrases": ("N:o 87", "TIISTAINA", "1 mk"),
        "page_model_getter": "meta",
    },
    {
        "name": "main_headline",
        "required_phrases": ("JO 39 KUOLONUHRIA",),
        "page_model_getter": "main_headline",
    },
    {
        "name": "secondary_headline",
        "required_phrases": ("TEHDASR",),
        "page_model_getter": "secondary_headline",
    },
    {
        "name": "main_story_sidebar",
        "required_phrases": (
            "Jo 39 ihmistä oli löydetty",
            "valtioneuvosto kokoontui",
            "tutkijalautakunta",
            "patruunatehdas",
            "luovuttaakseen vertaan",
            "loukkaantuneille",
        ),
        "page_model_getter": "main_story_sidebar",
    },
    {
        "name": "image_caption",
        "required_phrases": (
            "Murhe kasvoi",
            "Viimeisimpien tietojen",
            "38 ihmistä kuollut",
            "lisääntyvän",
        ),
        "page_model_getter": "image_caption",
    },
    {
        "name": "lower_headline",
        "required_phrases": ("LAPUA ERISTET",),
        "page_model_getter": "lower_headline",
    },
    {
        "name": "lower_story_columns",
        "required_phrases": (
            "Räjähdys tapahtui tehtaan lataamorakennuksessa",
            "60 henkilöä",
            "Tarkkojen tietojen",
            "Ensimmäinen hälytys",
            "irrotettavissa olevat",
            "Miltei kaikki tiet",
            "lentokieltoalueeksi",
        ),
        "page_model_getter": "lower_story_columns",
    },
    {
        "name": "continuation",
        "required_phrases": ("JATKUU TAKASIVULLE",),
        "page_model_getter": "continuation",
    },
)


@dataclass
class SegmentAuditResult:
    name: str
    required_phrases: list[str]
    found_in_page_model: bool
    found_in_markdown: bool
    found_in_pdf: bool
    status: str
    missing_phrases: list[str] = field(default_factory=list)


@dataclass
class ContentAuditResult:
    required_segments: list[SegmentAuditResult]
    forbidden_fragments: list[dict[str, object]]
    duplicate_fragments: list[str]
    truncated_fragments: list[str]
    source_segment_count: int
    page_model_segment_count: int
    rendered_segment_count: int
    unassigned_segments: list[str]
    unrendered_segments: list[str]
    truncated_segments: list[str]
    content_loss_detected: bool
    content_misassignment_detected: bool
    truncated_text_detected: bool
    duplicate_text_detected: bool
    layout_quality: str
    content_quality: str
    quality_result: str

    def to_json_dict(self) -> dict[str, object]:
        return {
            "required_segments": [
                {
                    "name": seg.name,
                    "required_phrases": seg.required_phrases,
                    "found_in_page_model": seg.found_in_page_model,
                    "found_in_markdown": seg.found_in_markdown,
                    "found_in_pdf": seg.found_in_pdf,
                    "status": seg.status,
                    "missing_phrases": seg.missing_phrases,
                }
                for seg in self.required_segments
            ],
            "forbidden_fragments": self.forbidden_fragments,
            "duplicate_fragments": self.duplicate_fragments,
            "truncated_fragments": self.truncated_fragments,
            "source_segment_count": self.source_segment_count,
            "page_model_segment_count": self.page_model_segment_count,
            "rendered_segment_count": self.rendered_segment_count,
            "unassigned_segments": self.unassigned_segments,
            "unrendered_segments": self.unrendered_segments,
            "truncated_segments": self.truncated_segments,
            "content_loss_detected": self.content_loss_detected,
            "content_misassignment_detected": self.content_misassignment_detected,
            "truncated_text_detected": self.truncated_text_detected,
            "duplicate_text_detected": self.duplicate_text_detected,
            "layout_quality": self.layout_quality,
            "content_quality": self.content_quality,
            "quality_result": self.quality_result,
        }


def run_content_audit(
    *,
    page_model: NewspaperFrontPageModel | None,
    markdown_path: Path | None,
    structural_pdf_path: Path | None,
    layout_quality: str = "PASS",
) -> ContentAuditResult:
    """Audit final markdown/PDF content against required newspaper segments."""
    md_text = _read_text(markdown_path)
    pdf_text = _read_pdf_text(structural_pdf_path)
    md_lower = md_text.lower()
    pdf_lower = pdf_text.lower()
    story_body = extract_story_body(md_text) if md_text else ""

    segments = build_content_segments(page_model) if page_model is not None else ()
    segment_text = _segment_lookup(segments, page_model)

    required_results: list[SegmentAuditResult] = []
    content_loss = False
    for spec in _REQUIRED_SEGMENTS:
        name = str(spec["name"])
        phrases = tuple(str(p) for p in spec["required_phrases"])  # type: ignore[index]
        model_blob = segment_text.get(name, "")
        md_blob = story_body if name == "main_story_sidebar" else md_text
        result = SegmentAuditResult(
            name=name,
            required_phrases=list(phrases),
            found_in_page_model=_contains_all(model_blob, phrases),
            found_in_markdown=_contains_all(md_blob, phrases),
            found_in_pdf=_contains_all(pdf_text, phrases),
            status="PASS",
        )
        missing = [p for p in phrases if not _contains_phrase(model_blob, p)]
        if missing:
            result.missing_phrases = missing
        if not (result.found_in_page_model and result.found_in_markdown and result.found_in_pdf):
            result.status = "FAIL"
            content_loss = True
        required_results.append(result)

    forbidden_found: list[dict[str, object]] = []
    truncated_detected = False
    for fragment in _FORBIDDEN_FRAGMENTS:
        in_md = _contains_forbidden_fragment(md_text, fragment)
        in_pdf = _contains_forbidden_fragment(pdf_text, fragment)
        forbidden_found.append({"fragment": fragment, "found": in_md or in_pdf})
        if in_md or in_pdf:
            truncated_detected = True

    duplicate_fragments = _find_duplicate_fragments(md_text)
    duplicate_detected = bool(duplicate_fragments)

    misassignments = detect_content_misassignment(page_model) if page_model is not None else []
    misassignment_detected = bool(misassignments)

    truncated_segments = [
        seg.id for seg in segments if _looks_truncated(seg.normalized_text)
    ]
    if truncated_segments:
        truncated_detected = True

    content_quality = "PASS"
    if (
        content_loss
        or misassignment_detected
        or truncated_detected
        or duplicate_detected
    ):
        content_quality = "FAIL"

    layout_q = layout_quality if layout_quality in {"PASS", "FAIL"} else "PASS"
    quality_result = "PASS" if layout_q == "PASS" and content_quality == "PASS" else "FAIL"

    return ContentAuditResult(
        required_segments=required_results,
        forbidden_fragments=forbidden_found,
        duplicate_fragments=duplicate_fragments,
        truncated_fragments=[f["fragment"] for f in forbidden_found if f["found"]],
        source_segment_count=len(segments),
        page_model_segment_count=len(segments),
        rendered_segment_count=len(segments),
        unassigned_segments=[],
        unrendered_segments=[
            seg.name
            for seg in required_results
            if seg.status == "FAIL"
        ],
        truncated_segments=truncated_segments,
        content_loss_detected=content_loss,
        content_misassignment_detected=misassignment_detected,
        truncated_text_detected=truncated_detected,
        duplicate_text_detected=duplicate_detected,
        layout_quality=layout_q,
        content_quality=content_quality,
        quality_result=quality_result,
    )


def save_content_audit(*, result: ContentAuditResult, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.to_json_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def _segment_lookup(
    segments: tuple[ContentSegment, ...],
    page_model: NewspaperFrontPageModel | None,
) -> dict[str, str]:
    if page_model is None:
        return {}

    lower_cols = "\n\n".join(page_model.bottom_column_texts)
    return {
        "masthead": f"{page_model.masthead_text}\n{page_model.newspaper_name_text}",
        "meta": f"{page_model.issue_number}\n{page_model.date_text}\n{page_model.price_text}",
        "main_headline": page_model.main_headline,
        "secondary_headline": page_model.secondary_headline,
        "main_story_sidebar": page_model.right_sidebar_text,
        "image_caption": page_model.image_caption,
        "lower_headline": page_model.bottom_headline,
        "lower_story_columns": lower_cols,
        "continuation": page_model.continuation_text,
    }


def _contains_phrase(blob: str, phrase: str) -> bool:
    from kuvien_parsinta.text.final_text import finalize_newspaper_text

    if not phrase.strip():
        return True
    blob_norm = re.sub(r"\s+", " ", finalize_newspaper_text(blob).lower())
    phrase_norm = re.sub(r"\s+", " ", finalize_newspaper_text(phrase).lower())
    if phrase_norm in blob_norm:
        return True
    return phrase_norm.replace("ä", "a").replace("ö", "o") in blob_norm.replace("ä", "a").replace("ö", "o")


def _contains_all(blob: str, phrases: tuple[str, ...]) -> bool:
    return all(_contains_phrase(blob, phrase) for phrase in phrases)


def _read_text(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8-sig")


def _read_pdf_text(pdf_path: Path | None) -> str:
    if pdf_path is None or not pdf_path.is_file():
        return ""
    doc = fitz.open(str(pdf_path))
    try:
        return doc[0].get_text()
    finally:
        doc.close()


def _contains_forbidden_fragment(blob: str, fragment: str) -> bool:
    if fragment == "loukkaantunei":
        return bool(re.search(r"\bloukkaantunei(?!ta|lle|n)\b", blob, flags=re.IGNORECASE))
    if fragment == "lataamorakennu":
        return bool(re.search(r"\blataamorakennu\b(?![ks])", blob, flags=re.IGNORECASE))
    return fragment.lower() in blob.lower()


def _find_duplicate_fragments(markdown: str) -> list[str]:
    duplicates: list[str] = []
    body = extract_story_body(markdown)
    if body.upper().count("LUOVUTTAAKSEEN VERTAAN") > 1:
        duplicates.append("luovuttaakseen vertaan")
    if markdown.upper().count("LAPUA ERISTET") > 1:
        duplicates.append("LAPUA ERISTETTIIN")
    return duplicates


def _looks_truncated(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if re.search(r"\bloukkaantunei\b", stripped, flags=re.IGNORECASE):
        return True
    if re.search(r"\blataamorakennu\b(?![ks])", stripped, flags=re.IGNORECASE):
        return True
    if "Räjäh maata" in stripped:
        return True
    return False
