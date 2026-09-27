$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

function Step($Message) {
    Write-Host "`n=== $Message ===" -ForegroundColor Cyan
}

function Require-Success($Message) {
    if ($LASTEXITCODE -ne 0) { throw $Message }
}

Step "Checking the NUMAN checkout"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git is not installed or is not on PATH. Install Git for Windows, then rerun this updater."
}
& git rev-parse --is-inside-work-tree *> $null
Require-Success "This folder is not a Git checkout. Ask Andy to reinstall NUMAN from GitHub."
$Branch = (& git branch --show-current).Trim()
Require-Success "Could not determine the current Git branch."
if ($Branch -ne "main") {
    throw "NUMAN is on branch '$Branch', not 'main'. Ask Andy to inspect it before updating."
}
$LocalChanges = & git status --porcelain
Require-Success "Could not inspect local changes."
if ($LocalChanges) {
    Write-Warning "This installation has local changes. Git will preserve them and stop if the update overlaps them."
}

Step "Downloading the latest NUMAN release"
& git pull --ff-only origin main
Require-Success "Git could not fast-forward to origin/main. No local files were forcibly replaced. Ask Andy for help."

Step "Refreshing NUMAN's Python packages"
$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "NUMAN's private Python environment is missing. Run SETUP-NUMAN.cmd instead."
}
& $Python -m pip install --upgrade -e ".[dev,live,api,wake]"
Require-Success "Python packages could not be updated."

Step "Preparing wake phrases"
& .\.venv\Scripts\numan.exe wake compile
Require-Success "Wake phrases could not be rebuilt. Run SETUP-NUMAN.cmd or ask Andy for help."

Step "Validating the updated installation"
& .\.venv\Scripts\numan.exe config validate --live
Require-Success "The updated code does not accept the current configuration. Ask Andy for help."
& .\.venv\Scripts\numan.exe doctor
if ($LASTEXITCODE -eq 0) {
    Write-Host "`nNUMAN is up to date and ready." -ForegroundColor Green
} else {
    Write-Warning "The update succeeded, but the readiness check found an item that needs attention."
}
