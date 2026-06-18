"""System font registration for newspaper structural PDF."""

from __future__ import annotations

from pathlib import Path

from kuvien_parsinta.pdf.layout_pdf import LayoutPreservingPDF

_FONT_CANDIDATES: tuple[tuple[str, str, Path], ...] = (
    ("Ar", "", Path("C:/Windows/Fonts/arial.ttf")),
    ("Ar", "B", Path("C:/Windows/Fonts/arialbd.ttf")),
    ("Ar", "I", Path("C:/Windows/Fonts/ariali.ttf")),
    ("Ar", "BI", Path("C:/Windows/Fonts/arialbi.ttf")),
    ("ArBlk", "", Path("C:/Windows/Fonts/ariblk.ttf")),
    ("Tm", "", Path("C:/Windows/Fonts/times.ttf")),
    ("Tm", "B", Path("C:/Windows/Fonts/timesbd.ttf")),
    ("Tm", "I", Path("C:/Windows/Fonts/timesi.ttf")),
    ("Tm", "BI", Path("C:/Windows/Fonts/timesbi.ttf")),
    ("Ge", "", Path("C:/Windows/Fonts/georgia.ttf")),
    ("Ge", "B", Path("C:/Windows/Fonts/georgiab.ttf")),
    ("Ge", "I", Path("C:/Windows/Fonts/georgiai.ttf")),
    ("Ge", "BI", Path("C:/Windows/Fonts/georgiaz.ttf")),
)


def _font_key(family: str, style: str) -> str:
    return family.lower() + "".join(sorted(style.upper()))


def font_is_registered(pdf: LayoutPreservingPDF, family: str, style: str) -> bool:
    """Return True when family/style is available on the PDF instance."""
    return _font_key(family, style) in pdf.fonts


def register_newspaper_fonts(pdf: LayoutPreservingPDF) -> None:
    """Register Windows system fonts used by typography roles."""
    pdf.register_fonts()
    for family, style, path in _FONT_CANDIDATES:
        if not path.is_file():
            continue
        try:
            pdf.add_font(family, style, str(path))
        except RuntimeError:
            continue
