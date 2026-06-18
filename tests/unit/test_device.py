"""Unit tests for compute device resolution."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from kuvien_parsinta.device import (
    onnxruntime_providers,
    preferred_torch_device,
    resolve_paddle_device,
)


def test_resolve_paddle_device_explicit_gpu() -> None:
    assert resolve_paddle_device("gpu:0") == "gpu:0"
    assert resolve_paddle_device("cpu") == "cpu"


@patch("kuvien_parsinta.device._paddle_cuda_available", return_value=True)
def test_resolve_paddle_device_auto_uses_gpu_when_available(_mock: MagicMock) -> None:
    assert resolve_paddle_device("auto") == "gpu:0"


@patch("kuvien_parsinta.device._paddle_cuda_available", return_value=False)
def test_resolve_paddle_device_auto_falls_back_to_cpu(_mock: MagicMock) -> None:
    assert resolve_paddle_device("auto") == "cpu"


def test_preferred_torch_device_cpu_when_cuda_unavailable() -> None:
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = False
    with patch.dict(sys.modules, {"torch": mock_torch}):
        assert preferred_torch_device() == "cpu"


def test_preferred_torch_device_cuda_when_available() -> None:
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = True
    with patch.dict(sys.modules, {"torch": mock_torch}):
        assert preferred_torch_device() == "cuda"


def test_onnxruntime_providers_gpu_first() -> None:
    mock_ort = MagicMock()
    mock_ort.get_available_providers.return_value = [
        "CPUExecutionProvider",
        "CUDAExecutionProvider",
    ]
    with patch.dict(sys.modules, {"onnxruntime": mock_ort}):
        assert onnxruntime_providers() == (
            "CUDAExecutionProvider",
            "CPUExecutionProvider",
        )
