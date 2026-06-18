"""Safe import behaviour for optional PaddleOCR-VL."""

from __future__ import annotations

import builtins
from unittest.mock import MagicMock, patch

import pytest

from kuvien_parsinta.engines.paddleocr_vl_engine import VlNotInstalledError, _load_paddleocr_vl_class


def test_vl_import_error_message() -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "paddleocr":
            raise ImportError("mock missing paddleocr")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=fake_import):
        with pytest.raises(VlNotInstalledError, match="install_paddleocr_vl"):
            _load_paddleocr_vl_class()


def test_vl_import_success() -> None:
    fake_module = MagicMock()
    fake_module.PaddleOCRVL = object
    with patch.dict("sys.modules", {"paddleocr": fake_module}):
        cls = _load_paddleocr_vl_class()
    assert cls is object
