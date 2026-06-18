#Requires -Version 5.1
<#
.SYNOPSIS
  Upgrade repo venv to CUDA-enabled PyTorch (cu118, matches paddlepaddle-gpu).

.USAGE
  git clone https://github.com/FoxRav/doclayout-ai.git
  cd doclayout-ai
  powershell -ExecutionPolicy Bypass -File scripts\install_cuda.ps1
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Pip = Join-Path $RepoRoot ".venv\Scripts\pip.exe"
if (-not (Test-Path $Python)) {
    Write-Error ".venv not found. Run scripts\setup.ps1 first."
}

Write-Host "=== CUDA stack (PyTorch cu118 + ONNX GPU) ===" -ForegroundColor Cyan

Write-Host "Installing torch 2.5.1+cu118 (matches paddle cu118) ..."
& $Pip install --upgrade --force-reinstall `
    "torch==2.5.1" "torchvision==0.20.1" `
    --index-url https://download.pytorch.org/whl/cu118

Write-Host "Ensuring onnxruntime-gpu ..."
& $Pip install --upgrade "onnxruntime-gpu>=1.19"

& "$RepoRoot\scripts\install_dll_hook.ps1"

Write-Host "`n=== verify_env.py ===" -ForegroundColor Cyan
& $Python "$RepoRoot\scripts\verify_env.py"
if ($LASTEXITCODE -ne 0) {
    Write-Error "CUDA verify failed"
}

Write-Host "`n=== CUDA OK ===" -ForegroundColor Green
Write-Host "Paddle OCR uses PARSE_OCR_DEVICE=auto (GPU when available)."
