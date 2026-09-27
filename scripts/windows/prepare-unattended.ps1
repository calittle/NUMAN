# Prepare machine-local copies without changing the running interactive installation.
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RuntimeRoot = Join-Path $env:ProgramData "NUMAN"
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
Set-Location $ProjectRoot
if (Get-Process python,pythonw,ollama -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$RuntimeRoot\*" }) {
    throw "Stop the NUMAN-Show task before refreshing its runtime."
}
function Copy-Tree($Source, $Destination) {
    if (-not (Test-Path -LiteralPath $Source)) { throw "Missing source: $Source" }
    & robocopy $Source $Destination /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP
    if ($LASTEXITCODE -ge 8) { throw "Could not copy $Source (robocopy $LASTEXITCODE)." }
}
$SourcePython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PythonHome = (& $SourcePython -c "import sys; print(sys.base_prefix)").Trim()
if ($LASTEXITCODE -ne 0) { throw "Run SETUP-NUMAN.cmd first." }
New-Item -ItemType Directory -Force $RuntimeRoot | Out-Null
Copy-Tree $PythonHome (Join-Path $RuntimeRoot "python")
$SharedPython = Join-Path $RuntimeRoot "python\python.exe"
& $SharedPython -m venv (Join-Path $RuntimeRoot "venv")
if ($LASTEXITCODE -ne 0) { throw "Could not create the show environment." }
Copy-Tree (Join-Path $ProjectRoot ".venv\Lib\site-packages") (Join-Path $RuntimeRoot "venv\Lib\site-packages")
# Regenerate launchers: copying venv Scripts would retain calit's interpreter path.
$RebuildScripts = @"
import importlib.metadata
import pathlib
import sys
from pip._vendor.distlib.scripts import ScriptMaker
maker = ScriptMaker(None, str(pathlib.Path(sys.executable).parent))
maker.executable = sys.executable
maker.clobber = True
maker.variants = {''}
for distribution in importlib.metadata.distributions():
    for entry in distribution.entry_points:
        if entry.group == 'console_scripts':
            maker.make(f'{entry.name} = {entry.value}')
"@
$ShowPython = Join-Path $RuntimeRoot "venv\Scripts\python.exe"
& $ShowPython -c $RebuildScripts
if ($LASTEXITCODE -ne 0) { throw "Could not regenerate Python command launchers." }
$OllamaCommand = Get-Command ollama -ErrorAction Stop
$OllamaHome = Split-Path $OllamaCommand.Source
New-Item -ItemType Directory -Force (Join-Path $RuntimeRoot "ollama") | Out-Null
Copy-Item -LiteralPath (Join-Path $OllamaHome "ollama.exe") -Destination (Join-Path $RuntimeRoot "ollama\ollama.exe") -Force
Copy-Tree (Join-Path $OllamaHome "lib") (Join-Path $RuntimeRoot "ollama\lib")
$ModelSource = if ($env:OLLAMA_MODELS) { $env:OLLAMA_MODELS } else { Join-Path $env:USERPROFILE ".ollama\models" }
Copy-Tree $ModelSource (Join-Path $RuntimeRoot "models")
$FFmpeg = (Get-Command ffmpeg -ErrorAction Stop).Source
New-Item -ItemType Directory -Force (Join-Path $RuntimeRoot "bin") | Out-Null
Copy-Item -LiteralPath $FFmpeg -Destination (Join-Path $RuntimeRoot "bin\ffmpeg.exe") -Force
New-Item -ItemType Directory -Force (Join-Path $RuntimeRoot "logs") | Out-Null
$env:Path = (Join-Path $RuntimeRoot "bin") + ";" + $env:Path
& $ShowPython -c "import sys, sentencepiece, sherpa_onnx, edge_tts; print('Shared interpreter:', sys.executable); print('Base runtime:', sys.base_prefix)"
if ($LASTEXITCODE -ne 0) { throw "Shared runtime verification failed." }
& $ShowPython -m numan config validate --live
if ($LASTEXITCODE -ne 0) { throw "Show configuration validation failed." }
Write-Host "Shared runtime prepared at $RuntimeRoot. Run ENABLE-UNATTENDED.cmd next."
