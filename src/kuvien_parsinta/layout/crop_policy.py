"""Rules for which layout regions may be embedded as raster crops in structural PDFs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Sequence

from kuvien_parsinta.layout.page_layout import BboxPx, LayoutBlock, NewspaperBlockType

PhotoRole = Literal["hero_image", "photo", "illustration", "map", "figure"]

_PHOTO_BLOCK_TYPES: frozenset[NewspaperBlockType] = frozenset({NewspaperBlockType.HERO_IMAGE})

_PHOTO_ROLE_NAMES: frozenset[str] = frozenset(
    {"hero_image", "photo", "illustration", "map", "figure"}
)

_TEXT_ROLE_SUBSTRINGS: tuple[str, ...] = (
    "text",
    "headline",
    "masthead",
    "meta",
    "caption",
    "body",
    "continuation",
    "sidebar",
    "newspaper",
    "issue",
    "footer",
)

_FORBIDDEN_BLOCK_TYPES: frozenset[NewspaperBlockType] = frozenset(
    {
        NewspaperBlockType.MASTHEAD_LOGO,
        NewspaperBlockType.NEWSPAPER_NAME,
        NewspaperBlockType.ISSUE_META,
        NewspaperBlockType.MAIN_HEADLINE,
        NewspaperBlockType.SECONDARY_HEADLINE,
        NewspaperBlockType.IMAGE_CAPTION,
        NewspaperBlockType.RIGHT_SIDEBAR,
        NewspaperBlockType.BOTTOM_HEADLINE,
        NewspaperBlockType.BOTTOM_COLUMNS,
        NewspaperBlockType.CONTINUATION_BOX,
        NewspaperBlockType.BODY_TEXT,
        NewspaperBlockType.FOOTER_BAR,
    }
)

_TEXT_COVERAGE_THRESHOLD = 0.15


class CropBlock(Protocol):
    """Minimal block surface for crop policy evaluation."""

    @property
    def role(self) -> str: ...

    @property
    def bbox(self) -> BboxPx: ...

    @property
    def text(self) -> str: ...


@dataclass(frozen=True, slots=True)
class LayoutCropBlock:
    role: str
    bbox: BboxPx
    text: str

    @classmethod
    def from_layout_block(cls, block: LayoutBlock) -> LayoutCropBlock:
        return cls(
            role=block.block_type.value,
            bbox=block.bbox_px,
            text=block.text,
        )


@dataclass(frozen=True, slots=True)
class CropPolicySettings:
    render_text_as_image: bool = False
    allow_text_crops: bool = False
    allow_photo_crops: bool = True


def _intersection_area(a: BboxPx, b: BboxPx) -> float:
    x1 = max(a.x1, b.x1)
    y1 = max(a.y1, b.y1)
    x2 = min(a.x2, b.x2)
    y2 = min(a.y2, b.y2)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    return (x2 - x1) * (y2 - y1)


def text_coverage_ratio(
    block: CropBlock,
    ocr_blocks: Sequence[CropBlock] | None = None,
) -> float:
    """Share of crop area covered by OCR text bounding boxes."""
    crop_area = block.bbox.area
    if crop_area <= 0:
        return 1.0

    candidates = list(ocr_blocks) if ocr_blocks else [block]
    text_area = 0.0
    for candidate in candidates:
        if not candidate.text.strip():
            continue
        text_area += _intersection_area(candidate.bbox, block.bbox)

    return min(1.0, text_area / crop_area)


def _role_is_text_like(role: str) -> bool:
    lowered = role.lower()
    return any(token in lowered for token in _TEXT_ROLE_SUBSTRINGS)


def can_crop_as_image(
    block: CropBlock,
    *,
    settings: CropPolicySettings | None = None,
    ocr_blocks: Sequence[CropBlock] | None = None,
) -> bool:
    """Return True only when the region is a photo-like raster, not text."""
    policy = settings or CropPolicySettings()
    if not policy.allow_photo_crops:
        return False
    if policy.render_text_as_image or policy.allow_text_crops:
        return False

    role = block.role.lower()
    if _role_is_text_like(role):
        return False
    if role not in _PHOTO_ROLE_NAMES and role != NewspaperBlockType.HERO_IMAGE.value:
        return False

    ratio = text_coverage_ratio(block, ocr_blocks)
    if ratio > _TEXT_COVERAGE_THRESHOLD:
        return False

    if block.text.strip() and len(block.text.strip()) > 12:
        alpha = sum(ch.isalpha() for ch in block.text)
        if alpha / max(len(block.text), 1) > 0.35:
            return False

    return True


def can_crop_layout_block(
    block: LayoutBlock,
    *,
    settings: CropPolicySettings | None = None,
    ocr_blocks: Sequence[LayoutBlock] | None = None,
) -> bool:
    """LayoutBlock adapter for crop policy."""
    if block.block_type in _FORBIDDEN_BLOCK_TYPES:
        return False
    if block.block_type not in _PHOTO_BLOCK_TYPES:
        return False

    crop_block = LayoutCropBlock.from_layout_block(block)
    ocr_crop_blocks = (
        tuple(LayoutCropBlock.from_layout_block(item) for item in ocr_blocks)
        if ocr_blocks is not None
        else None
    )
    return can_crop_as_image(crop_block, settings=settings, ocr_blocks=ocr_crop_blocks)


def crop_policy_from_settings(settings: object) -> CropPolicySettings:
    """Build policy from application Settings."""
    return CropPolicySettings(
        render_text_as_image=bool(getattr(settings, "render_text_as_image", False)),
        allow_text_crops=bool(getattr(settings, "allow_text_crops", False)),
        allow_photo_crops=bool(getattr(settings, "allow_photo_crops", True)),
    )
