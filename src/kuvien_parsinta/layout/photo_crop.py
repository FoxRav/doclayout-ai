"""Detect and crop embedded photographs from document scans."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class CropRect:
    x: int
    y: int
    width: int
    height: int

    def clamp(self, *, max_width: int, max_height: int) -> CropRect:
        x = max(0, min(self.x, max_width - 1))
        y = max(0, min(self.y, max_height - 1))
        width = max(1, min(self.width, max_width - x))
        height = max(1, min(self.height, max_height - y))
        return CropRect(x=x, y=y, width=width, height=height)


def detect_embedded_photo(
    image_path: Path,
    text_polys: Sequence[Sequence[Sequence[float]]] | None,
) -> CropRect | None:
    """Find the largest non-text photo-like region in a scan."""
    image = cv2.imread(str(image_path))
    if image is None:
        return None

    height, width = image.shape[:2]
    image_area = width * height
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    text_mask = _text_mask(width=width, height=height, text_polys=text_polys)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 17))
    text_mask = cv2.dilate(text_mask, kernel, iterations=2)

    non_text = cv2.bitwise_not(text_mask)
    not_margin = (gray < 245).astype(np.uint8) * 255
    texture = (np.abs(cv2.Laplacian(gray, cv2.CV_64F)) > 4.0).astype(np.uint8) * 255

    candidate = cv2.bitwise_and(non_text, not_margin)
    candidate = cv2.bitwise_and(candidate, texture)

    contours, _ = cv2.findContours(candidate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best: CropRect | None = None
    best_score = 0.0

    for contour in contours:
        x, y, box_w, box_h = cv2.boundingRect(contour)
        area = box_w * box_h
        area_ratio = area / image_area
        if area_ratio < 0.04 or area_ratio > 0.55:
            continue
        aspect = box_w / max(box_h, 1)
        if aspect < 0.35 or aspect > 2.8:
            continue
        if _touches_border(
            x, y, box_w, box_h, image_width=width, image_height=height, margin=8
        ):
            continue

        score = area_ratio
        if 0.55 <= aspect <= 1.8:
            score += 0.08
        if 0.10 <= area_ratio <= 0.30:
            score += 0.10
        if x < width * 0.55:
            score += 0.03

        if score > best_score:
            best_score = score
            best = CropRect(x=x, y=y, width=box_w, height=box_h)

    if best is None:
        return None
    return _refine_photo_bbox(
        gray=gray,
        text_mask=_text_mask(width=width, height=height, text_polys=text_polys),
        crop=best.clamp(max_width=width, max_height=height),
    )


def crop_embedded_photo(
    *,
    image_path: Path,
    text_polys: Sequence[Sequence[Sequence[float]]] | None,
    output_path: Path,
) -> CropRect | None:
    """Detect photo region, crop, and save. Returns crop box or None."""
    crop = detect_embedded_photo(image_path, text_polys)
    if crop is None:
        return None
    return crop_photo_by_rect(image_path=image_path, crop=crop, output_path=output_path)


def crop_photo_by_rect(
    *,
    image_path: Path,
    crop: CropRect,
    output_path: Path,
) -> CropRect:
    """Crop a known rectangle and save."""
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Image not readable: {image_path}")
    height, width = image.shape[:2]
    clamped = crop.clamp(max_width=width, max_height=height)
    cropped = image[
        clamped.y : clamped.y + clamped.height,
        clamped.x : clamped.x + clamped.width,
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), cropped)
    return clamped


def _text_mask(
    *,
    width: int,
    height: int,
    text_polys: Sequence[Sequence[Sequence[float]]] | None,
) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    if not text_polys:
        return mask
    for poly in text_polys:
        points = np.array([[int(point[0]), int(point[1])] for point in poly], dtype=np.int32)
        if len(points) >= 3:
            cv2.fillPoly(mask, [points], 255)
    return mask


def _touches_border(
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    image_width: int,
    image_height: int,
    margin: int,
) -> bool:
    on_left = x <= margin
    on_top = y <= margin
    on_right = x + width >= image_width - margin
    on_bottom = y + height >= image_height - margin
    return sum((on_left, on_top, on_right, on_bottom)) >= 3


def _refine_photo_bbox(
    *,
    gray: np.ndarray,
    text_mask: np.ndarray,
    crop: CropRect,
) -> CropRect:
    """Tighten an oversized contour to the main photo component."""
    region_gray = gray[crop.y : crop.y + crop.height, crop.x : crop.x + crop.width]
    region_text = text_mask[crop.y : crop.y + crop.height, crop.x : crop.x + crop.width]
    if region_gray.size == 0:
        return crop

    texture = (np.abs(cv2.Laplacian(region_gray, cv2.CV_64F)) > 12.0).astype(np.uint8) * 255
    not_text = cv2.bitwise_not(region_text)
    candidate = cv2.bitwise_and(texture, not_text)

    count, _, stats, _ = cv2.connectedComponentsWithStats(candidate, connectivity=8)
    best: CropRect | None = None
    best_score = 0.0
    min_area = max(5_000, int(crop.width * crop.height * 0.08))

    for label in range(1, count):
        x, y, box_w, box_h, area = stats[label]
        if area < min_area:
            continue
        aspect = box_w / max(box_h, 1)
        if aspect < 0.45 or aspect > 1.9:
            continue
        score = float(area)
        if 0.65 <= aspect <= 1.35:
            score *= 1.15
        if score > best_score:
            best_score = score
            best = CropRect(
                x=crop.x + int(x),
                y=crop.y + int(y),
                width=int(box_w),
                height=int(box_h),
            )

    if best is None:
        return crop
    return best
