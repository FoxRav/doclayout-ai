"""Fixed-layout page model for newspaper / poster facsimile PDF rendering."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DocumentType(str, Enum):
    GENERIC = "generic"
    NEWSPAPER_FRONT_PAGE = "newspaper_front_page"


class NewspaperBlockType(str, Enum):
    MASTHEAD_LOGO = "masthead_logo"
    NEWSPAPER_NAME = "newspaper_name"
    ISSUE_META = "issue_meta"
    MAIN_HEADLINE = "main_headline"
    SECONDARY_HEADLINE = "secondary_headline"
    HERO_IMAGE = "hero_image"
    IMAGE_CAPTION = "image_caption"
    RIGHT_SIDEBAR = "right_sidebar"
    BOTTOM_HEADLINE = "bottom_headline"
    BOTTOM_COLUMNS = "bottom_columns"
    CONTINUATION_BOX = "continuation_box"
    FOOTER_BAR = "footer_bar"
    BODY_TEXT = "body_text"
    MARGIN_ARTIFACT = "margin_artifact"
    UNKNOWN = "unknown"


class FontRole(str, Enum):
    MASTHEAD = "masthead"
    HEADLINE = "headline"
    BODY = "body"
    CAPTION = "caption"
    META = "meta"


class BlockRenderMode(str, Enum):
    IMAGE = "image"
    TEXT = "text"
    HIDDEN_TEXT = "hidden_text"
    BOX = "box"


@dataclass(frozen=True, slots=True)
class BboxPx:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2.0


@dataclass(frozen=True, slots=True)
class BboxPt:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)


@dataclass(frozen=True, slots=True)
class LayoutBlock:
    id: str
    block_type: NewspaperBlockType
    bbox_px: BboxPx
    bbox_pdf: BboxPt
    text: str
    source_engine: str
    confidence: float
    reading_order: int
    font_role: FontRole
    render_mode: BlockRenderMode


@dataclass(frozen=True, slots=True)
class PageLayout:
    page_width_px: int
    page_height_px: int
    pdf_width_pt: float
    pdf_height_pt: float
    scale_x: float
    scale_y: float
    document_type: DocumentType
    blocks: tuple[LayoutBlock, ...]


@dataclass(frozen=True, slots=True)
class LayoutQualityMetrics:
    document_type: DocumentType
    pdf_mode: str
    layout_preserve: bool
    source_aspect_ratio: float
    pdf_aspect_ratio: float
    main_headline_found: bool
    hero_image_found: bool
    right_sidebar_found: bool
    bottom_columns_found: bool
    reflow_used: bool
    visible_text_overlay: bool
    debug_boxes_visible: bool
    visible_ocr: bool
    raster_similarity_to_source: float | None
    warnings: tuple[str, ...]

    def to_compare_fields(self) -> dict[str, object]:
        fields: dict[str, object] = {
            "document_type": self.document_type.value,
            "pdf_mode": self.pdf_mode,
            "layout_preserve": self.layout_preserve,
            "source_aspect_ratio": round(self.source_aspect_ratio, 4),
            "pdf_aspect_ratio": round(self.pdf_aspect_ratio, 4),
            "main_headline_found": self.main_headline_found,
            "hero_image_found": self.hero_image_found,
            "right_sidebar_found": self.right_sidebar_found,
            "bottom_columns_found": self.bottom_columns_found,
            "reflow_used": self.reflow_used,
            "visible_text_overlay": self.visible_text_overlay,
            "debug_boxes_visible": self.debug_boxes_visible,
            "visible_ocr": self.visible_ocr,
            "warnings": list(self.warnings),
        }
        if self.raster_similarity_to_source is not None:
            fields["raster_similarity_to_source"] = round(self.raster_similarity_to_source, 4)
        return fields
