"""Unit tests for structural PDF crop policy."""

from __future__ import annotations

from kuvien_parsinta.layout.crop_policy import (
    CropPolicySettings,
    LayoutCropBlock,
    can_crop_as_image,
    text_coverage_ratio,
)
from kuvien_parsinta.layout.page_layout import BboxPx, LayoutBlock, NewspaperBlockType


def _block(block_type: NewspaperBlockType, text: str = "") -> LayoutBlock:
    from kuvien_parsinta.layout.page_layout import BlockRenderMode, BboxPt, FontRole

    bbox = BboxPx(x1=0, y1=0, x2=100, y2=100)
    return LayoutBlock(
        id="test",
        block_type=block_type,
        bbox_px=bbox,
        bbox_pdf=BboxPt(0, 0, 100, 100),
        text=text,
        source_engine="test",
        confidence=0.9,
        reading_order=0,
        font_role=FontRole.BODY,
        render_mode=BlockRenderMode.TEXT,
    )


def test_masthead_block_cannot_be_cropped() -> None:
    block = LayoutCropBlock.from_layout_block(
        _block(NewspaperBlockType.MASTHEAD_LOGO, "KUVA ERIKOIS")
    )
    assert can_crop_as_image(block) is False


def test_hero_image_can_be_cropped_when_low_text_coverage() -> None:
    block = LayoutCropBlock(role="hero_image", bbox=BboxPx(0, 0, 200, 200), text="")
    assert can_crop_as_image(block, settings=CropPolicySettings()) is True


def test_text_coverage_ratio_high_for_text_block() -> None:
    block = LayoutCropBlock(
        role="masthead",
        bbox=BboxPx(0, 0, 100, 100),
        text="ILTA-SANOMAT",
    )
    assert text_coverage_ratio(block) >= 0.15
