from pathlib import Path

from kuvien_parsinta.models import InputKind
from kuvien_parsinta.router import detect_input_kind, primary_engine_for_kind
from kuvien_parsinta.fallback import ParseEngine


def test_detect_image() -> None:
    assert detect_input_kind(Path("x.PNG")) is InputKind.IMAGE


def test_detect_pdf() -> None:
    assert detect_input_kind(Path("doc.pdf")) is InputKind.PDF


def test_engine_image() -> None:
    assert primary_engine_for_kind(InputKind.IMAGE) is ParseEngine.PP_STRUCTURE
