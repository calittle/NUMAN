param(
    [switch]$SkipWindowsApps,
    [switch]$SkipModels,
    [switch]$Interactive,
    [switch]$ConfigureUnattended
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
    throw "Python is missing. Install 64-bit Python 3.13 from python.org, check 'Add Python to PATH', reopen PowerShell, and rerun this script."
}
& py -3.13 -c "import sys; print(sys.version); raise SystemExit(sys.version_info[:2] != (3, 13))"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.13 is required so both local Piper and Kokoro voices are supported. Install 64-bit Python 3.13 from python.org and rerun this script."
}

Install-WingetApp "git" "Git.Git" "Git"
Install-WingetApp "ffmpeg" "Gyan.FFmpeg" "FFmpeg"
Install-WingetApp "ollama" "Ollama.Ollama" "Ollama"
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

Step "Creating NUMAN's private Python environment"
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & py -3.13 -m venv .venv
} else {
    & .\.venv\Scripts\python.exe -c "import sys; raise SystemExit(sys.version_info[:2] != (3, 13))"
    if ($LASTEXITCODE -ne 0) {
        throw "The existing .venv was created with a Python version other than 3.13. Rename or remove .venv, then rerun setup."
    }
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".[dev,live,local-tts,api,wake]"
if ($LASTEXITCODE -ne 0) { throw "NUMAN's Python packages could not be installed." }

Step "Checking the Microsoft Visual C++ runtime"
$RuntimeProbe = @"
import ctypes
import sys
try:
    for name in ('msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'):
        ctypes.WinDLL(name)
except OSError:
    sys.exit(1)
"@
& .\.venv\Scripts\python.exe -c $RuntimeProbe
if ($LASTEXITCODE -ne 0) {
    if ($SkipWindowsApps) { throw "The Visual C++ runtime is missing. Rerun setup without -SkipWindowsApps." }
    $RuntimeArch = (& .\.venv\Scripts\python.exe -c "import platform; print({'AMD64': 'x64', 'ARM64': 'arm64', 'x86': 'x86'}.get(platform.machine(), ''))").Trim()
    if (-not $RuntimeArch) { throw "Cannot determine the Visual C++ runtime architecture." }
    $RuntimeInstaller = Join-Path $env:TEMP "numan-vc-redist-$RuntimeArch.exe"
    Download-WithRetry "https://aka.ms/vc14/vc_redist.$RuntimeArch.exe" $RuntimeInstaller "the Microsoft Visual C++ runtime" 1MB
    $RuntimeInstall = Start-Process -FilePath $RuntimeInstaller -ArgumentList "/install", "/passive", "/norestart" -WindowStyle Hidden -Wait -PassThru
    if ($RuntimeInstall.ExitCode -eq 3010) { throw "Restart Windows to finish installing the Visual C++ runtime, then rerun SETUP-NUMAN.cmd." }
    if ($RuntimeInstall.ExitCode -notin @(0, 1638)) { throw "Visual C++ runtime installation failed (exit $($RuntimeInstall.ExitCode))." }
}
& .\.venv\Scripts\python.exe -c "import sentencepiece; import sherpa_onnx"
if ($LASTEXITCODE -ne 0) { throw "Wake-word libraries could not load. Repair the Microsoft Visual C++ Redistributable, restart Windows, and rerun setup." }

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
    if ((-not (Test-Path "tools\whisper\whisper-cli.exe")) -or (-not (Test-Path "tools\whisper\whisper-server.exe"))) {
        # Stable whisper.cpp releases do not always publish binary assets. Search
        # recent official releases (including their official nightly builds) for
        # the newest normal Windows x64 package instead of assuming /latest has it.
        $Releases = Invoke-RestMethod "https://api.github.com/repos/ggml-org/whisper.cpp/releases?per_page=20"
        $Asset = $null
        foreach ($Release in $Releases) {
            $Asset = $Release.assets | Where-Object {
                $_.name -eq "whisper-bin-x64.zip"
            } | Select-Object -First 1
            if ($Asset) {
                Write-Host "Using official whisper.cpp release $($Release.tag_name)."
                break
            }
        }
        if (-not $Asset) { throw "No recent official whisper.cpp release contained the normal 64-bit Windows package. See docs/ROB-GUIDE.md." }
        $Archive = Join-Path $env:TEMP "numan-whisper.zip"
        $Extracted = Join-Path $env:TEMP "numan-whisper"
        Download-WithRetry $Asset.browser_download_url $Archive "whisper.cpp for Windows"
        Remove-Item $Extracted -Recurse -Force -ErrorAction SilentlyContinue
        Expand-Archive $Archive -DestinationPath $Extracted -Force
        $Executable = Get-ChildItem $Extracted -Recurse -Filter "whisper-cli.exe" | Select-Object -First 1
        if (-not $Executable) { throw "whisper-cli.exe was not found in the downloaded archive." }
        New-Item -ItemType Directory -Force -Path "tools\whisper" | Out-Null
        Copy-Item (Join-Path $Executable.Directory.FullName "*") "tools\whisper" -Recurse -Force
        if (-not (Test-Path "tools\whisper\whisper-server.exe")) {
            throw "whisper-server.exe was not found in the downloaded whisper.cpp package."
        }
        Remove-Item $Archive -Force -ErrorAction SilentlyContinue
        Remove-Item $Extracted -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "whisper.cpp is already present."
    }

    Step "Downloading the wake-word model"
    $WakeName = "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
    $WakeFolder = Join-Path "models" $WakeName
    if (-not (Test-Path (Join-Path $WakeFolder "tokens.txt"))) {
        $WakeArchive = Join-Path $env:TEMP "$WakeName.tar.bz2"
        Download-WithRetry "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/$WakeName.tar.bz2" $WakeArchive "the wake-word model"
        Remove-Item $WakeFolder -Recurse -Force -ErrorAction SilentlyContinue
        # Windows' bundled tar.exe cannot always launch a bzip2 decompressor.
        # Python's standard tarfile module handles this archive without an
        # additional system utility, and Python is already required by NUMAN.
        & .\.venv\Scripts\python.exe -m tarfile -e $WakeArchive models
        if (($LASTEXITCODE -ne 0) -or (-not (Test-Path (Join-Path $WakeFolder "tokens.txt")))) {
            throw "Could not unpack the wake-word model. Rerun SETUP-NUMAN.cmd to retry."
        }
        Remove-Item $WakeArchive -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "Wake-word model is already present."
    }

    Step "Downloading local voice models"
    & .\.venv\Scripts\numan.exe voice models install
    if ($LASTEXITCODE -ne 0) {
        throw "The Piper and Kokoro voice models could not be installed or verified."
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
& .\.venv\Scripts\numan.exe voice cache build
if ($LASTEXITCODE -ne 0) { throw "The deterministic voice cache could not be prepared." }
& .\.venv\Scripts\numan.exe doctor
if ($LASTEXITCODE -eq 0) {
    Write-Host "`nSetup is complete. NUMAN is ready." -ForegroundColor Green
    $EnableStartup = $ConfigureUnattended
    if ($Interactive -and -not $EnableStartup) {
        $Answer = Read-Host "Configure automatic login and unattended startup for a dedicated NumanShow account? (y/N)"
        $EnableStartup = $Answer -match '^(?i:y|yes)$'
    }
    if ($EnableStartup) {
        Step "Configuring unattended show startup"
        & (Join-Path $PSScriptRoot "configure-unattended.ps1")
    }
} else {
    Write-Warning "Setup finished, but something still needs attention. Follow the FIX line above or see docs\ROB-GUIDE.md."
}
