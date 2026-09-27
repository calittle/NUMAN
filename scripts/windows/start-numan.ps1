$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

if (-not (Test-Path ".venv\Scripts\numan.exe")) {
    Write-Host "NUMAN is not installed yet. Double-click scripts\windows\SETUP-NUMAN.cmd first." -ForegroundColor Red
    exit 1
}

Write-Host "Starting NUMAN. Say 'Hey Captain Grog' or 'Hey Polly'." -ForegroundColor Green
Write-Host "Keep this window open. Press Ctrl-C once to stop." -ForegroundColor Yellow
& .\.venv\Scripts\numan.exe wake run --live
