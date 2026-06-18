"""Layout-aware document structuring and embedded photo detection."""

from kuvien_parsinta.layout.from_structure import (
    markdown_from_structure,
    structure_document_from_json,
    structure_document_from_parsing,
)
from kuvien_parsinta.layout.photo_crop import CropRect, crop_embedded_photo, crop_photo_by_rect, detect_embedded_photo
from kuvien_parsinta.layout.structure import (
    LayoutBlockKind,
    StructuredBlock,
    StructuredDocument,
    column_split_threshold,
    detect_multi_column,
    structure_document_from_ocr,
    structured_to_markdown,
)

__all__ = [
    "CropRect",
    "crop_embedded_photo",
    "crop_photo_by_rect",
    "detect_embedded_photo",
    "LayoutBlockKind",
    "StructuredBlock",
    "StructuredDocument",
    "column_split_threshold",
    "detect_multi_column",
    "markdown_from_structure",
    "structure_document_from_json",
    "structure_document_from_ocr",
    "structure_document_from_parsing",
    "structured_to_markdown",
]
