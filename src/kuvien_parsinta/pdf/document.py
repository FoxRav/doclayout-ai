"""PDF that mirrors the detected layout of a scanned document."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import cv2

from kuvien_parsinta.layout.structure import (
    LayoutBlockKind,
    StructuredBlock,
    StructuredDocument,
)
from kuvien_parsinta.pdf.render import BODY_GRAY, ArticlePDF

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
_COLUMN_GAP_MM = 6.0


class DocumentPDF(ArticlePDF):
    def render_structured_document(
        self,
        document: StructuredDocument,
        *,
        photo_path: Path | None = None,
    ) -> None:
        """Render one page: title, optional photo, and column text like the scan."""
        self.add_page()

        self.set_font("Ar", "B", 18)
        self.set_text_color(*BODY_GRAY)
        self.multi_cell(0, 8, document.title, align="C")
        self.ln(6)

        left_blocks = _column_blocks(document, column_index=0)
        right_blocks = _column_blocks(document, column_index=1)
        other_blocks = [
            block
            for block in document.blocks
            if block.kind is not LayoutBlockKind.COLUMN
            and block.kind is not LayoutBlockKind.META
        ]

        if document.is_multi_column and (left_blocks or right_blocks or photo_path):
            self._render_two_column_layout(
                left_blocks=left_blocks,
                right_blocks=right_blocks,
                photo_path=photo_path,
            )
        else:
            if photo_path is not None:
                self._render_inline_photo(photo_path, width=None)
                self.ln(4)
            for block in other_blocks:
                self._render_block(block)
            for block in left_blocks + right_blocks:
                self._render_block(block)

    def _render_two_column_layout(
        self,
        *,
        left_blocks: list[StructuredBlock],
        right_blocks: list[StructuredBlock],
        photo_path: Path | None,
    ) -> None:
        gap_mm = _COLUMN_GAP_MM
        col_w = (self.w - self.l_margin - self.r_margin - gap_mm) / 2
        left_x = self.l_margin
        right_x = self.l_margin + col_w + gap_mm
        start_y = self.get_y()

        left_y = start_y
        if photo_path is not None:
            left_y = self._render_inline_photo(
                photo_path,
                width=col_w,
                x=left_x,
                y=start_y,
            )
            left_y += 3.0

        self.set_xy(left_x, left_y)
        for block in left_blocks:
            self._render_block(block, width=col_w, x=left_x)
        left_end_y = self.get_y()

        self.set_xy(right_x, start_y)
        for block in right_blocks:
            self._render_block(block, width=col_w, x=right_x)
        right_end_y = self.get_y()

        self.set_y(max(left_end_y, right_end_y) + 4)

    def _render_inline_photo(
        self,
        photo_path: Path,
        *,
        width: float | None,
        x: float | None = None,
        y: float | None = None,
    ) -> float:
        pos_x = x if x is not None else self.l_margin
        pos_y = y if y is not None else self.get_y()
        usable_w = width if width is not None else (self.w - self.l_margin - self.r_margin)
        self.set_xy(pos_x, pos_y)
        self.image(str(photo_path), x=pos_x, y=pos_y, w=usable_w)
        return pos_y + _image_height_mm(photo_path, usable_w)

    def _render_block(
        self,
        block: StructuredBlock,
        *,
        width: float | None = None,
        x: float | None = None,
    ) -> None:
        if block.kind is LayoutBlockKind.META:
            return
        pos_x = x if x is not None else self.l_margin
        for paragraph in block.paragraphs:
            self.set_x(pos_x)
            self.set_font("Ar", "", 10)
            if width is not None:
                self.multi_cell(width, 5, paragraph)
            else:
                self.multi_cell(0, 5.5, paragraph)
            self.ln(2)


def _column_blocks(document: StructuredDocument, *, column_index: int) -> list[StructuredBlock]:
    return [
        block
        for block in document.blocks
        if block.kind is LayoutBlockKind.COLUMN and block.column_index == column_index
    ]


def _image_height_mm(photo_path: Path, width_mm: float) -> float:
    image = cv2.imread(str(photo_path))
    if image is None:
        return width_mm
    height_px, width_px = image.shape[:2]
    if width_px <= 0:
        return width_mm
    return width_mm * (height_px / width_px)


def render_document_pdf(
    *,
    source_path: Path,
    document: StructuredDocument,
    pdf_path: Path,
    text_polys: Sequence[Sequence[Sequence[float]]] | None = None,
    photo_crop_path: Path | None = None,
) -> Path:
    _ = text_polys
    if source_path.suffix.lower() not in _IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image source for document PDF: {source_path.suffix}")

    from kuvien_parsinta.layout.from_structure import save_embedded_photo

    embedded_photo = photo_crop_path
    if document.embedded_photo is not None:
        if embedded_photo is None or not embedded_photo.is_file():
            default_crop = pdf_path.parent / f"{source_path.stem}_photo.jpg"
            save_embedded_photo(
                image_path=source_path,
                document=document,
                output_path=default_crop,
            )
            embedded_photo = default_crop if default_crop.is_file() else None

    pdf = DocumentPDF()
    pdf.register_fonts()
    pdf.render_structured_document(document, photo_path=embedded_photo)

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(pdf_path))
    return pdf_path
