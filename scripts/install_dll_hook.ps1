# Copy torch/Paddle DLL coexistence hook into the repo venv only.
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvSite = Join-Path $RepoRoot ".venv\Lib\site-packages"
if (-not (Test-Path $VenvSite)) {
    Write-Error ".venv not found. Run scripts/setup.ps1 first."
}
Copy-Item (Join-Path $PSScriptRoot "_paddleocr_preload.py") (Join-Path $VenvSite "_paddleocr_preload.py") -Force
Copy-Item (Join-Path $PSScriptRoot "_paddleocr_torch_dll_fix.pth") (Join-Path $VenvSite "_paddleocr_torch_dll_fix.pth") -Force
Write-Host "Installed DLL preload hook to $VenvSite"
