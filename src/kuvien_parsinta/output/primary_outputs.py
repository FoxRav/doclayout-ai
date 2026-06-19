"""Centralized primary output writer (markdown + optional PDFs)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kuvien_parsinta.config import Settings
from kuvien_parsinta.layout.newspaper_page_model import NewspaperPageModel
from kuvien_parsinta.markdown.newspaper_markdown import resolve_primary_markdown
from kuvien_parsinta.models import InputKind, ParseResult

_MARKDOWN_ENCODING = "utf-8-sig"


@dataclass(frozen=True, slots=True)
class PrimaryOutputPaths:
    markdown_path: Path
    structural_pdf_path: Path | None = None
    facsimile_pdf_path: Path | None = None
    clean_pdf_path: Path | None = None
    layout_debug_path: Path | None = None
    structural_debug_path: Path | None = None
    structural_report_path: Path | None = None
    search_text_path: Path | None = None
    pdf_path: Path | None = None


def write_markdown(*, path: Path, markdown_text: str) -> Path:
    """Write primary markdown with UTF-8 BOM for Windows compatibility."""
    content = markdown_text.strip()
    if not content:
        raise RuntimeError("primary markdown output was not written")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n", encoding=_MARKDOWN_ENCODING)
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError("primary markdown output was not written")
    return path


def write_primary_outputs(
    *,
    source: Path,
    target_dir: Path,
    engine_markdown: str,
    result: ParseResult,
    settings: Settings,
    kind: InputKind,
    layout: object | None,
    vl_json: Path | None,
    pdf_render_fn: object,
    newspaper_model: NewspaperPageModel | None = None,
) -> PrimaryOutputPaths:
    """Write mandatory markdown; delegate optional PDF/debug outputs."""
    from kuvien_parsinta.layout.page_layout import PageLayout

    page_layout = layout if isinstance(layout, PageLayout) else None
    vl_path = vl_json if vl_json is not None and vl_json.is_file() else None
    markdown_text = resolve_primary_markdown(
        engine_markdown=engine_markdown,
        layout=page_layout,
        vl_json_path=vl_path,
        source_path=source,
        tmp_dir=settings.debug_dir(target_dir) / ".tmp_crops" if page_layout else None,
        newspaper_model=newspaper_model,
    )
    md_path = write_markdown(path=target_dir / f"{source.stem}.md", markdown_text=markdown_text)

    pdf_paths: dict[str, Path | None] = {
        "pdf_path": None,
        "structural_pdf_path": None,
        "facsimile_pdf_path": None,
        "clean_pdf_path": None,
        "layout_debug_path": None,
        "structural_debug_path": None,
        "structural_report_path": None,
        "search_text_path": None,
    }
    if settings.write_pdf and kind is InputKind.IMAGE and callable(pdf_render_fn):
        pdf_paths = pdf_render_fn(
            source=source,
            md_path=md_path,
            target_dir=target_dir,
            result=result,
            settings=settings,
            layout=page_layout,
            vl_json=vl_json,
            newspaper_model=newspaper_model,
        )

    return PrimaryOutputPaths(
        markdown_path=md_path,
        structural_pdf_path=pdf_paths.get("structural_pdf_path"),
        facsimile_pdf_path=pdf_paths.get("facsimile_pdf_path"),
        clean_pdf_path=pdf_paths.get("clean_pdf_path"),
        layout_debug_path=pdf_paths.get("layout_debug_path"),
        structural_debug_path=pdf_paths.get("structural_debug_path"),
        structural_report_path=pdf_paths.get("structural_report_path"),
        search_text_path=pdf_paths.get("search_text_path"),
        pdf_path=pdf_paths.get("pdf_path"),
    )


def has_utf8_bom(path: Path) -> bool:
    raw = path.read_bytes()
    return raw.startswith(b"\xef\xbb\xbf")
