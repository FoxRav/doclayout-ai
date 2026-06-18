"""Verify isolated parse environment (repo .venv only)."""

from __future__ import annotations

import importlib
import sys
from typing import Iterable


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


def _check(names: Iterable[str]) -> list[str]:
    failed: list[str] = []
    for name in names:
        try:
            mod = importlib.import_module(name)
            ver = getattr(mod, "__version__", "ok")
            print(f"  OK    {name:22s} {ver}")
        except Exception as exc:
            print(f"  FAIL  {name:22s} {type(exc).__name__}: {exc}")
            failed.append(name)
    return failed


def main() -> int:
    _section("Python (expect repo .venv)")
    print(sys.executable)
    print(sys.version)
    if "95.Kuvien-parsinta-SOTA" not in sys.executable.replace("\\", "/"):
        print("  WARN  Interpreter path does not look like repo .venv")

    failed: list[str] = []

    _section("Paddle GPU")
    try:
        import paddle

        print(f"  paddle {paddle.__version__} cuda={paddle.is_compiled_with_cuda()}")
        if paddle.is_compiled_with_cuda():
            print(f"  devices={paddle.device.cuda.device_count()}")
        paddle.utils.run_check()
        print("  OK    paddle.utils.run_check()")
    except Exception as exc:
        print(f"  FAIL  paddle {type(exc).__name__}: {exc}")
        failed.append("paddle")

    _section("PyTorch CUDA")
    try:
        import torch

        cuda_ok = torch.cuda.is_available()
        print(f"  torch {torch.__version__} cuda={cuda_ok}")
        if cuda_ok:
            print(f"  device={torch.cuda.get_device_name(0)}")
            print("  OK    torch.cuda.is_available()")
        else:
            print("  WARN  torch installed but CUDA not available (VL path will use CPU)")
    except Exception as exc:
        print(f"  FAIL  torch {type(exc).__name__}: {exc}")
        failed.append("torch")

    _section("ONNX Runtime")
    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
        print(f"  providers={providers}")
        if "CUDAExecutionProvider" in providers:
            print("  OK    CUDAExecutionProvider available")
        else:
            print("  WARN  CUDAExecutionProvider missing — GPU ONNX models use CPU")
    except Exception as exc:
        print(f"  FAIL  onnxruntime {type(exc).__name__}: {exc}")
        failed.append("onnxruntime")

    _section("OCR stack")
    failed.extend(
        _check(
            (
                "paddleocr",
                "paddlex",
                "paddleformers",
                "torch",
                "albumentations",
                "pypdfium2",
                "fpdf",
                "fitz",
            )
        )
    )

    _section("This package")
    failed.extend(_check(("kuvien_parsinta",)))

    _section("CLI")
    try:
        from kuvien_parsinta.cli import app

        print(f"  OK    kuvien-parsinta CLI ({app.info.name})")
    except Exception as exc:
        print(f"  FAIL  CLI {type(exc).__name__}: {exc}")
        failed.append("cli")

    if failed:
        print(f"\nFAILED: {', '.join(failed)}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
