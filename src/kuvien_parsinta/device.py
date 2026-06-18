"""Compute device selection: prefer CUDA/GPU when available and beneficial."""

from __future__ import annotations

import os
from functools import lru_cache


def resolve_paddle_device(configured: str) -> str:
    """Map settings value to a PaddleOCR device string.

    ``auto`` picks ``gpu:0`` when Paddle sees a CUDA device, otherwise ``cpu``.
    Explicit values (``gpu:0``, ``cpu``, ``gpu:1``, …) are passed through unchanged.
    """
    normalized = configured.strip().lower()
    if normalized and normalized != "auto":
        return configured.strip()

    if _paddle_cuda_available():
        return "gpu:0"
    return "cpu"


def preferred_torch_device() -> str:
    """Return ``cuda`` or ``cpu`` for PyTorch-based models (e.g. VL fallback)."""
    try:
        import torch
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def onnxruntime_providers(*, prefer_gpu: bool = True) -> tuple[str, ...]:
    """Execution providers for ONNX Runtime, GPU first when available."""
    try:
        import onnxruntime as ort
    except ImportError:
        return ("CPUExecutionProvider",)

    available = set(ort.get_available_providers())
    if not prefer_gpu:
        return ("CPUExecutionProvider",)

    ordered: list[str] = []
    for provider in (
        "CUDAExecutionProvider",
        "TensorrtExecutionProvider",
        "CPUExecutionProvider",
    ):
        if provider in available:
            ordered.append(provider)
    return tuple(ordered) if ordered else ("CPUExecutionProvider",)


def configure_cuda_runtime(*, device_index: int = 0) -> None:
    """Set process-wide CUDA hints for ONNX Runtime and PyTorch."""
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", str(device_index))
    os.environ.setdefault("ORT_CUDA_DEVICE_ID", str(device_index))


@lru_cache(maxsize=1)
def _paddle_cuda_available() -> bool:
    try:
        import paddle
    except ImportError:
        return False
    if not paddle.is_compiled_with_cuda():
        return False
    try:
        return paddle.device.cuda.device_count() > 0
    except (RuntimeError, OSError):
        return False
