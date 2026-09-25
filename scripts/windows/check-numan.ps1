$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

if (-not (Test-Path ".venv\Scripts\numan.exe")) {
    Write-Host "NUMAN is not installed. Double-click scripts\windows\SETUP-NUMAN.cmd first." -ForegroundColor Red
    exit 1
}

& .\.venv\Scripts\numan.exe doctor
Write-Host "`nPress Enter to close this window."
Read-Host
