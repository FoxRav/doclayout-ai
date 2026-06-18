#Requires -Version 5.1
<#
.SYNOPSIS
  One-shot setup: isolated .venv inside this repo (does NOT touch system Python).

.USAGE
  git clone https://github.com/FoxRav/doclayout-ai.git
  cd doclayout-ai
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
  .\scripts\activate.ps1
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "=== doclayout-ai setup ===" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"
Write-Host "All packages install ONLY into: $RepoRoot\.venv" -ForegroundColor Yellow

# --- Python 3.10 venv ---
$Py = $null
foreach ($candidate in @("py -3.10", "python")) {
    try {
        $ver = Invoke-Expression "$candidate -c `"import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')`""
        if ($ver -eq "3.10") {
            $Py = $candidate
            break
        }
    } catch { continue }
}
if (-not $Py) {
    Write-Error "Python 3.10 required. Install 3.10.x and retry."
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating .venv ..."
    Invoke-Expression "$Py -m venv .venv"
}

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Pip = Join-Path $RepoRoot ".venv\Scripts\pip.exe"

& $Python -m pip install --upgrade pip setuptools wheel

# --- Warn if both CPU and GPU Paddle are present ---
$pipList = & $Pip list 2>$null | Out-String
if ($pipList -match "paddlepaddle-gpu" -and $pipList -match "(?m)^paddlepaddle\s") {
    Write-Warning "Both paddlepaddle and paddlepaddle-gpu detected in venv. Keep only one."
}

# --- PaddleOCR upstream (inside repo) ---
$PaddleDir = Join-Path $RepoRoot "PaddleOCR"
if (-not (Test-Path $PaddleDir)) {
    Write-Host "Cloning PaddleOCR (shallow) ..."
    git clone --depth 1 https://github.com/PaddlePaddle/PaddleOCR.git $PaddleDir
}

# --- GPU Paddle (CUDA 11.8) ---
Write-Host "Installing paddlepaddle-gpu (cu118) ..."
& $Pip install --upgrade "paddlepaddle-gpu>=3.3.1" `
    -i https://www.paddlepaddle.org.cn/packages/stable/cu118/

# --- Editable PaddleOCR ---
Write-Host "Installing paddleocr[all] editable ..."
& $Pip install -e "$PaddleDir[all]"

# --- OCR extras + torch (CUDA 11.8 — matches paddlepaddle-gpu) ---
Write-Host "Installing OCR extras ..."
& $Pip install -r "$RepoRoot\requirements\ocr-extras.txt"

Write-Host "Installing torch 2.5.1+cu118 ..."
& $Pip install --upgrade --force-reinstall `
    "torch==2.5.1" "torchvision==0.20.1" `
    --index-url https://download.pytorch.org/whl/cu118

# --- This package ---
Write-Host "Installing kuvien-parsinta ..."
& $Pip install -e "$RepoRoot[pdf,dev]"

# --- DLL hook (Windows) ---
& "$RepoRoot\scripts\install_dll_hook.ps1"

# --- Config ---
if (-not (Test-Path "$RepoRoot\.env")) {
    Copy-Item "$RepoRoot\.env.example" "$RepoRoot\.env"
    Write-Host "Created .env from .env.example"
}

# --- Verify ---
Write-Host "`n=== verify_env.py ===" -ForegroundColor Cyan
& $Python "$RepoRoot\scripts\verify_env.py"
if ($LASTEXITCODE -ne 0) {
    Write-Error "verify_env failed"
}

Write-Host "`n=== pytest ===" -ForegroundColor Cyan
& $Python -m pytest "$RepoRoot\tests\unit" -q
if ($LASTEXITCODE -ne 0) {
    Write-Error "pytest failed"
}

Write-Host "`n=== DONE ===" -ForegroundColor Green
Write-Host "Activate:  .\.venv\Scripts\Activate.ps1"
Write-Host "Parse:     kuvien-parsinta parse parsittavat\example.jpg"
