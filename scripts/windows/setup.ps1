param(
    [switch]$SkipWindowsApps,
    [switch]$SkipModels
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

function Step($Message) {
    Write-Host "`n=== $Message ===" -ForegroundColor Cyan
}

function Install-WingetApp($CommandName, $PackageId, $FriendlyName) {
    if (Get-Command $CommandName -ErrorAction SilentlyContinue) {
        Write-Host "$FriendlyName is already installed."
        return
    }
    if ($SkipWindowsApps) {
        Write-Warning "$FriendlyName is missing. Install it before running NUMAN."
        return
    }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Windows Package Manager (winget) is missing. Install 'App Installer' from the Microsoft Store, then rerun this script."
    }
    $Installed = (& winget list --exact --id $PackageId --disable-interactivity 2>&1) | Out-String
    if ($Installed -match [regex]::Escape($PackageId)) {
        Write-Host "$FriendlyName is already installed. Its command should become available after setup refreshes PATH or Windows restarts."
        return
    }
    Step "Installing $FriendlyName"
    & winget install --exact --id $PackageId --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        $Installed = (& winget list --exact --id $PackageId --disable-interactivity 2>&1) | Out-String
        if ($Installed -notmatch [regex]::Escape($PackageId)) {
            throw "$FriendlyName installation failed."
        }
        Write-Host "$FriendlyName is installed; continuing despite winget's nonzero result."
    }
}

function Download-WithRetry($Uri, $OutFile, $FriendlyName, $MinimumBytes = 1) {
    $Partial = "$OutFile.partial"
    Remove-Item $Partial -Force -ErrorAction SilentlyContinue
    for ($Attempt = 1; $Attempt -le 3; $Attempt++) {
        try {
            Write-Host "Downloading $FriendlyName (attempt $Attempt of 3)..."
            Invoke-WebRequest -UseBasicParsing -Uri $Uri -OutFile $Partial
            if ((Get-Item $Partial).Length -lt $MinimumBytes) {
                throw "The downloaded file was unexpectedly small."
            }
            Move-Item $Partial $OutFile -Force
            return
        } catch {
            Remove-Item $Partial -Force -ErrorAction SilentlyContinue
            if ($Attempt -eq 3) {
                throw "Could not download $FriendlyName after 3 attempts. Check the internet connection and rerun SETUP-NUMAN.cmd. $($_.Exception.Message)"
            }
            Write-Warning "Could not download $FriendlyName. Retrying shortly. $($_.Exception.Message)"
            Start-Sleep -Seconds (3 * $Attempt)
        }
    }
}

Step "Checking Python"
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python is missing. Install Python 3.12 or newer from python.org, check 'Add Python to PATH', reopen PowerShell, and rerun this script."
}
& py -3 -c "import sys; print(sys.version); raise SystemExit(sys.version_info < (3, 12))"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.12 or newer is required. Install it from python.org and rerun this script."
}

Install-WingetApp "git" "Git.Git" "Git"
Install-WingetApp "ffmpeg" "Gyan.FFmpeg" "FFmpeg"
Install-WingetApp "ollama" "Ollama.Ollama" "Ollama"
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

Step "Creating NUMAN's private Python environment"
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & py -3 -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".[dev,live,api,wake]"
if ($LASTEXITCODE -ne 0) { throw "NUMAN's Python packages could not be installed." }

if (-not $SkipModels) {
    Step "Downloading the speech-recognition model"
    New-Item -ItemType Directory -Force -Path models | Out-Null
    $WhisperModel = "models\ggml-base.en.bin"
    if ((-not (Test-Path $WhisperModel)) -or ((Get-Item $WhisperModel).Length -lt 100MB)) {
        Remove-Item $WhisperModel -Force -ErrorAction SilentlyContinue
        Download-WithRetry "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin" $WhisperModel "the Whisper speech model" 100MB
    } else {
        Write-Host "Whisper model is already present."
    }

    Step "Installing the whisper.cpp command"
    if (-not (Test-Path "tools\whisper\whisper-cli.exe")) {
        $Release = Invoke-RestMethod "https://api.github.com/repos/ggml-org/whisper.cpp/releases/latest"
        $Asset = $Release.assets | Where-Object {
            $_.name -match '^whisper-bin-x64\.zip$'
        } | Select-Object -First 1
        if (-not $Asset) { throw "The official whisper.cpp release did not contain the normal 64-bit Windows package. See docs/ROB-GUIDE.md." }
        $Archive = Join-Path $env:TEMP "numan-whisper.zip"
        $Extracted = Join-Path $env:TEMP "numan-whisper"
        Download-WithRetry $Asset.browser_download_url $Archive "whisper.cpp for Windows"
        Remove-Item $Extracted -Recurse -Force -ErrorAction SilentlyContinue
        Expand-Archive $Archive -DestinationPath $Extracted -Force
        $Executable = Get-ChildItem $Extracted -Recurse -Filter "whisper-cli.exe" | Select-Object -First 1
        if (-not $Executable) { throw "whisper-cli.exe was not found in the downloaded archive." }
        New-Item -ItemType Directory -Force -Path "tools\whisper" | Out-Null
        Copy-Item (Join-Path $Executable.Directory.FullName "*") "tools\whisper" -Recurse -Force
        Remove-Item $Archive -Force -ErrorAction SilentlyContinue
        Remove-Item $Extracted -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "whisper.cpp is already present."
    }

    Step "Downloading the wake-word model"
    $WakeName = "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
    $WakeFolder = Join-Path "models" $WakeName
    if (-not (Test-Path (Join-Path $WakeFolder "tokens.txt"))) {
        if (-not (Get-Command tar -ErrorAction SilentlyContinue)) {
            throw "Windows tar is missing. Install current Windows updates, restart, and rerun setup."
        }
        $WakeArchive = Join-Path $env:TEMP "$WakeName.tar.bz2"
        Download-WithRetry "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/$WakeName.tar.bz2" $WakeArchive "the wake-word model"
        & tar -xf $WakeArchive -C models
        if ($LASTEXITCODE -ne 0) { throw "Could not unpack the wake-word model." }
        Remove-Item $WakeArchive -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "Wake-word model is already present."
    }
}

Step "Installing Ollama's NUMAN model"
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    & ollama pull llama3.2:3b
} else {
    Write-Warning "Ollama was installed but this PowerShell window cannot see it yet. Restart Windows, then run: ollama pull llama3.2:3b"
}

Step "Final check"
& .\.venv\Scripts\numan.exe wake compile
if ($LASTEXITCODE -ne 0) { throw "The wake phrases could not be prepared. Read the error above." }
& .\.venv\Scripts\numan.exe doctor
if ($LASTEXITCODE -eq 0) {
    Write-Host "`nSetup is complete. NUMAN is ready." -ForegroundColor Green
} else {
    Write-Warning "Setup finished, but something still needs attention. Follow the FIX line above or see docs\ROB-GUIDE.md."
}
