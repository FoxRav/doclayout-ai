#Requires -Version 5.1
<#
.SYNOPSIS
  Install PaddleOCR-VL doc-parser extras into the repo .venv.

.USAGE
  cd F:\-DEV-\95.Kuvien-parsinta-SOTA
  powershell -ExecutionPolicy Bypass -File scripts\install_paddleocr_vl.ps1
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Pip = Join-Path $RepoRoot ".venv\Scripts\pip.exe"
if (-not (Test-Path $Python)) {
    Write-Error ".venv not found. Run scripts\setup.ps1 first."
}

Write-Host "=== PaddleOCR-VL install ===" -ForegroundColor Cyan

& $Python -c "import sys; v=sys.version_info; assert (v.major,v.minor)==(3,10), f'Python 3.10 required, got {v.major}.{v.minor}'; print(f'Python {v.major}.{v.minor}.{v.micro} OK')"

$cpuPkg = & $Pip show paddlepaddle 2>$null
$gpuPkg = & $Pip show paddlepaddle-gpu 2>$null
if ($cpuPkg -and $gpuPkg) {
    Write-Host ""
    Write-Warning "Both paddlepaddle (CPU) and paddlepaddle-gpu are installed."
    Write-Warning "Do NOT keep both — uninstall one before production use:"
    Write-Host "  pip uninstall paddlepaddle" -ForegroundColor Yellow
    Write-Host "  OR pip uninstall paddlepaddle-gpu" -ForegroundColor Yellow
    Write-Host ""
}
if (-not $cpuPkg -and -not $gpuPkg) {
    Write-Host ""
    Write-Warning "PaddlePaddle is not installed in .venv."
    Write-Host "Run scripts\setup.ps1 first (installs paddlepaddle-gpu for CUDA)." -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "Installing paddleocr[doc-parser]>=3.4.0 ..."
& $Pip install -r "$RepoRoot\requirements\ocr-vl.txt"

Write-Host "`n=== VL smoke test ===" -ForegroundColor Cyan
$testImage = $null
$candidates = @(
    (Join-Path $RepoRoot "parsittavat\Koivisto_001\koivisto2_0-1280x1280.jpg"),
    (Join-Path $RepoRoot "parsittavat\Kuulutus\kuulutus.jpg")
)
foreach ($path in $candidates) {
    if (Test-Path $path) {
        $testImage = $path
        break
    }
}

if (-not $testImage) {
    Write-Warning "No local test image found under parsittavat/. Skipping predict smoke test."
    Write-Host "Install complete. Run: kuvien-parsinta parse <kuva> --engine vl" -ForegroundColor Green
    exit 0
}

& $Python -c @"
from pathlib import Path
from paddleocr import PaddleOCRVL
from kuvien_parsinta.device import resolve_paddle_device

image = Path(r'$testImage')
device = resolve_paddle_device('auto')
print(f'Test image: {image}')
print(f'Device: {device}')
pipeline = PaddleOCRVL(pipeline_version='v1.6', device=device)
results = pipeline.predict(str(image))
print(f'VL pages: {len(results)}')
if not results:
    raise SystemExit('VL smoke test returned no pages')
print('PaddleOCR-VL smoke test OK')
"@

if ($LASTEXITCODE -ne 0) {
    Write-Error "PaddleOCR-VL smoke test failed"
}

Write-Host "`n=== PaddleOCR-VL OK ===" -ForegroundColor Green
Write-Host "Try: kuvien-parsinta parse $testImage --engine vl"
