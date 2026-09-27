param([switch]$CheckOnly)
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RuntimeRoot = Join-Path $env:ProgramData "NUMAN"
$Python = Join-Path $RuntimeRoot "venv\Scripts\python.exe"
$LogRoot = Join-Path $RuntimeRoot "logs"
Set-Location $ProjectRoot
$env:Path = (Join-Path $RuntimeRoot "bin") + ";" + (Join-Path $RuntimeRoot "venv\Scripts") + ";" + $env:Path
$env:PYTHONUNBUFFERED = "1"
$env:OLLAMA_MODELS = Join-Path $RuntimeRoot "models"
$env:OLLAMA_HOST = "127.0.0.1:11434"
if (-not (Test-Path -LiteralPath $Python)) { throw "Run prepare-unattended.ps1 first." }
if ($CheckOnly) {
    & $Python -m numan doctor
    exit $LASTEXITCODE
}
$Mutex = New-Object System.Threading.Mutex($false, "Local\NUMAN-Unattended")
if (-not $Mutex.WaitOne(0)) { $Mutex.Dispose(); exit 0 }
New-Item -ItemType Directory -Force $LogRoot | Out-Null
$SupervisorLog = Join-Path $LogRoot "supervisor.log"
function Log($Message) { Add-Content -LiteralPath $SupervisorLog -Value "$(Get-Date -Format o) $Message" }
function Test-Ollama {
    try {
        $Response = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
        return $null -ne $Response.models
    } catch { return $false }
}
$OllamaProcess = $null
try {
    Log "Supervisor started as $env:USERDOMAIN\$env:USERNAME."
    while ($true) {
        try {
            if (-not (Test-Ollama)) {
                if (($null -eq $OllamaProcess) -or $OllamaProcess.HasExited) {
                    Log "Starting Ollama."
                    $OllamaProcess = Start-Process -FilePath (Join-Path $RuntimeRoot "ollama\ollama.exe") -ArgumentList "serve" -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $LogRoot "ollama.stdout.log") -RedirectStandardError (Join-Path $LogRoot "ollama.stderr.log")
                }
                $Ready = $false
                for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
                    if (Test-Ollama) { $Ready = $true; break }
                    Start-Sleep -Seconds 2
                }
                if (-not $Ready) { throw "Ollama is not ready; retrying shortly." }
            }
            $RunLog = Join-Path $LogRoot ("numan-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
            Log "Starting NUMAN; output: $RunLog"
            # Native stderr is diagnostic output, not a PowerShell terminating error.
            $ErrorActionPreference = "Continue"
            & $Python -u -m numan wake run --live >> $RunLog 2>&1
            $ExitCode = $LASTEXITCODE
            $ErrorActionPreference = "Stop"
            Log "NUMAN exited with code $ExitCode; restarting in 15 seconds."
        } catch {
            $ErrorActionPreference = "Stop"
            Log $_.Exception.Message
        }
        Start-Sleep -Seconds 15
    }
} finally {
    if (($null -ne $OllamaProcess) -and (-not $OllamaProcess.HasExited)) { $OllamaProcess.Kill() }
    $Mutex.ReleaseMutex()
    $Mutex.Dispose()
}
