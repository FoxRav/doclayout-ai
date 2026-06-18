"""Markdown → A4 PDF (Windows Arial). Ported from Lapua-RAG render_martti_magazine_pdf."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fpdf import FPDF

WIN_FONT_REG = Path("C:/Windows/Fonts/arial.ttf")
WIN_FONT_BOLD = Path("C:/Windows/Fonts/arialbd.ttf")
WIN_FONT_ITALIC = Path("C:/Windows/Fonts/ariali.ttf")
WIN_FONT_BI = Path("C:/Windows/Fonts/arialbi.ttf")

ACCENT = (118, 29, 36)
BODY_GRAY = (38, 38, 42)


def parse_md(text: str) -> list[tuple[str, Any]]:
    lines = text.splitlines()
    elements: list[tuple[str, Any]] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.strip() == "---":
            elements.append(("hr", None))
            i += 1
            continue
        if line.startswith("# "):
            elements.append(("h1", line[2:].strip()))
            i += 1
            continue
        if line.startswith("## "):
            elements.append(("h2", line[3:].strip()))
            i += 1
            continue
        if line.startswith("> "):
            quote_parts: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                quote_parts.append(lines[i].replace(">", "", 1).strip())
                i += 1
            elements.append(("quote", " ".join(quote_parts)))
            continue
        para = [line.strip()]
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if not nxt or nxt.startswith(("#", ">", "-", "---")):
                break
            para.append(nxt.strip())
            i += 1
        elements.append(("p", " ".join(para)))
    return elements


class ArticlePDF(FPDF):
    def __init__(self) -> None:
        super().__init__(unit="mm", format="A4")
        self.set_margins(22, 24, 22)
        self.set_auto_page_break(True, margin=24)

    def register_fonts(self) -> None:
        for path in (WIN_FONT_REG, WIN_FONT_BOLD, WIN_FONT_ITALIC, WIN_FONT_BI):
            if not path.is_file():
                raise FileNotFoundError(f"Font not found: {path}")
        self.add_font("Ar", "", str(WIN_FONT_REG))
        self.add_font("Ar", "B", str(WIN_FONT_BOLD))
        self.add_font("Ar", "I", str(WIN_FONT_ITALIC))
        self.add_font("Ar", "BI", str(WIN_FONT_BI))

    def render_title(self, title: str) -> None:
        self.add_page()
        self.set_font("Ar", "B", 22)
        self.set_text_color(*BODY_GRAY)
        self.multi_cell(0, 10, title, align="C")
        self.ln(16)
        self.set_text_color(*BODY_GRAY)

    def render_h2(self, text: str) -> None:
        self.set_x(self.l_margin)
        self.ln(6)
        self.set_font("Ar", "B", 13)
        self.multi_cell(0, 7, text)
        self.ln(4)

    def render_p(self, text: str) -> None:
        self.set_x(self.l_margin)
        self.set_font("Ar", "", 11)
        self.multi_cell(0, 5.5, text)
        self.ln(3)


def render_markdown_to_pdf(*, md_path: Path, pdf_path: Path) -> Path:
    md_text = md_path.read_text(encoding="utf-8")
    elements = parse_md(md_text)
    if not elements or elements[0][0] != "h1":
        raise ValueError("Markdown must start with a # title")

    pdf = ArticlePDF()
    pdf.register_fonts()
    pdf.render_title(elements[0][1])
    for kind, payload in elements[1:]:
        if kind == "h2":
            pdf.render_h2(payload)
        elif kind == "p":
            pdf.render_p(payload)
        elif kind == "quote":
            pdf.set_font("Ar", "I", 11)
            pdf.multi_cell(0, 6, payload)
            pdf.ln(3)

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(pdf_path))
    return pdf_path
