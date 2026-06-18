"""Pre-load torch runtime DLLs before PaddlePaddle (Windows only).

Installed into .venv/Lib/site-packages via scripts/install_dll_hook.ps1.
See docs/SETUP.md.
"""
from __future__ import annotations

import builtins
import ctypes
import os
import sys

_COOKIE_ATTR = "_PADDLEOCR_TORCH_DLL_COOKIE"


def _install() -> None:
    if not sys.platform.startswith("win"):
        return
    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is None:
        return
    torch_lib = os.path.join(sys.prefix, "lib", "site-packages", "torch", "lib")
    if not os.path.isdir(torch_lib):
        return

    os.environ["PATH"] = torch_lib + os.pathsep + os.environ.get("PATH", "")

    try:
        cookie = add_dll_directory(torch_lib)
    except OSError:
        return
    setattr(builtins, _COOKIE_ATTR, cookie)

    torch_python = os.path.join(torch_lib, "torch_python.dll")
    if os.path.isfile(torch_python):
        try:
            ctypes.WinDLL(torch_python)
        except OSError:
            pass


_install()
