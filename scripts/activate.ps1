# Convenience: activate repo venv (never use system Python for this project).
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Activate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $Activate)) {
    Write-Error "No .venv yet. Run: powershell -File scripts\setup.ps1"
}
. $Activate
Write-Host "Active: $RepoRoot\.venv" -ForegroundColor Green
Set-Location $RepoRoot
