"""OpenCV heuristics for newspaper front-page layout regions."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from kuvien_parsinta.layout.page_layout import BboxPx, DocumentType, NewspaperBlockType


@dataclass(frozen=True, slots=True)
class CandidateBlock:
    block_type: NewspaperBlockType
    bbox: BboxPx
    confidence: float


def detect_opencv_candidates(image_path: str | object) -> tuple[CandidateBlock, ...]:
    """Detect coarse newspaper regions using grayscale / morphology heuristics."""
    if isinstance(image_path, str):
        image = cv2.imread(image_path)
    else:
        image = image_path
    if image is None:
        return ()

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    if width <= 0 or height <= 0:
        return ()

    candidates: list[CandidateBlock] = []

    # Dark headline bands (upper page)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, dark = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, width // 40), 3))
    bands = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(bands, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    headline_idx = 0
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:12]:
        x, y, w, h = cv2.boundingRect(contour)
        if w < width * 0.45 or h < height * 0.015 or h > height * 0.12:
            continue
        rel_y = y / height
        if rel_y > 0.45:
            continue
        block_type = (
            NewspaperBlockType.MAIN_HEADLINE
            if headline_idx == 0
            else NewspaperBlockType.SECONDARY_HEADLINE
        )
        candidates.append(
            CandidateBlock(
                block_type=block_type,
                bbox=BboxPx(float(x), float(y), float(x + w), float(y + h)),
                confidence=0.55,
            )
        )
        headline_idx += 1
        if headline_idx >= 2:
            break

    # Hero image: low-edge middle-left region
    edges = cv2.Canny(blur, 40, 120)
    mid = gray[int(height * 0.18) : int(height * 0.72), int(width * 0.05) : int(width * 0.62)]
    if mid.size > 0:
        var = float(np.var(mid))
        if var > 900.0:
            candidates.append(
                CandidateBlock(
                    block_type=NewspaperBlockType.HERO_IMAGE,
                    bbox=BboxPx(
                        width * 0.05,
                        height * 0.22,
                        width * 0.62,
                        height * 0.72,
                    ),
                    confidence=0.5,
                )
            )

    # Right sidebar: narrow vertical text column
    right = dark[:, int(width * 0.72) :]
    if right.size > 0 and float(np.mean(right)) > 12.0:
        candidates.append(
            CandidateBlock(
                block_type=NewspaperBlockType.RIGHT_SIDEBAR,
                bbox=BboxPx(width * 0.72, height * 0.18, width * 0.97, height * 0.78),
                confidence=0.5,
            )
        )

    # Bottom columns
    bottom = dark[int(height * 0.72) :, :]
    if bottom.size > 0 and float(np.mean(bottom)) > 10.0:
        col_w = width / 4.0
        for idx in range(4):
            x1 = idx * col_w
            x2 = (idx + 1) * col_w - width * 0.02
            candidates.append(
                CandidateBlock(
                    block_type=NewspaperBlockType.BOTTOM_COLUMNS,
                    bbox=BboxPx(x1, height * 0.72, x2, height * 0.95),
                    confidence=0.45,
                )
            )

    # Continuation box bottom-right
    candidates.append(
        CandidateBlock(
            block_type=NewspaperBlockType.CONTINUATION_BOX,
            bbox=BboxPx(width * 0.78, height * 0.88, width * 0.97, height * 0.97),
            confidence=0.4,
        )
    )

    return tuple(candidates)


def is_newspaper_front_page(
    *,
    page_width: int,
    page_height: int,
    has_hero: bool,
    has_right_sidebar: bool,
    has_wide_headline: bool,
    has_bottom_columns: bool,
) -> bool:
    """Heuristic classifier for newspaper front pages."""
    score = 0
    if has_wide_headline:
        score += 2
    if has_hero:
        score += 2
    if has_right_sidebar:
        score += 2
    if has_bottom_columns:
        score += 1
    if page_width > 0 and page_height > 0:
        ratio = page_width / page_height
        if 0.65 <= ratio <= 1.4:
            score += 1
    return score >= 4


def document_type_from_signals(
    *,
    page_width: int,
    page_height: int,
    block_types: set[NewspaperBlockType],
) -> DocumentType:
    if is_newspaper_front_page(
        page_width=page_width,
        page_height=page_height,
        has_hero=NewspaperBlockType.HERO_IMAGE in block_types,
        has_right_sidebar=NewspaperBlockType.RIGHT_SIDEBAR in block_types,
        has_wide_headline=(
            NewspaperBlockType.MAIN_HEADLINE in block_types
            or NewspaperBlockType.SECONDARY_HEADLINE in block_types
        ),
        has_bottom_columns=NewspaperBlockType.BOTTOM_COLUMNS in block_types,
    ):
        return DocumentType.NEWSPAPER_FRONT_PAGE
    return DocumentType.GENERIC
