"""Input type detection and routing."""

from __future__ import annotations

from pathlib import Path

from kuvien_parsinta.fallback import ParseEngine
from kuvien_parsinta.models import InputKind

_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic"})
_PDF_SUFFIXES = frozenset({".pdf"})


def detect_input_kind(path: Path) -> InputKind:
    suffix = path.suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        return InputKind.IMAGE
    if suffix in _PDF_SUFFIXES:
        return InputKind.PDF
    return InputKind.UNKNOWN


def primary_engine_for_kind(kind: InputKind) -> ParseEngine:
    match kind:
        case InputKind.IMAGE:
            return ParseEngine.PP_STRUCTURE
        case InputKind.PDF:
            return ParseEngine.PP_STRUCTURE
        case InputKind.UNKNOWN:
            raise ValueError(f"Unsupported input type: {kind}")


def fallback_chain_for_kind(kind: InputKind, *, vl_enabled: bool) -> tuple[ParseEngine, ...]:
    match kind:
        case InputKind.IMAGE:
            chain: list[ParseEngine] = [ParseEngine.PP_STRUCTURE]
            if vl_enabled:
                chain.append(ParseEngine.PADDLE_VL)
            return tuple(chain)
        case InputKind.PDF:
            chain = [ParseEngine.NATIVE_PDF, ParseEngine.PP_STRUCTURE]
            if vl_enabled:
                chain.append(ParseEngine.PADDLE_VL)
            return tuple(chain)
        case InputKind.UNKNOWN:
            raise ValueError(f"Unsupported input type: {kind}")
