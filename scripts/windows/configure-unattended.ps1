param([switch]$SkipLightORama)
$ErrorActionPreference = "Stop"
$RuntimeRoot = Join-Path $env:ProgramData "NUMAN"
# Prepare while running as the installation user, whose packages/models are copied.
& (Join-Path $PSScriptRoot "prepare-unattended.ps1")
$AutologonRoot = Join-Path $RuntimeRoot "autologon"
$Autologon = Join-Path $AutologonRoot "Autologon64.exe"
New-Item -ItemType Directory -Force $AutologonRoot | Out-Null
if (-not (Test-Path -LiteralPath $Autologon)) {
    $Archive = Join-Path $AutologonRoot "AutoLogon.zip"
    for ($Attempt = 1; $Attempt -le 3; $Attempt++) {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri "https://download.sysinternals.com/files/AutoLogon.zip" -OutFile $Archive
            Expand-Archive -LiteralPath $Archive -DestinationPath $AutologonRoot -Force
            break
        } catch {
            if ($Attempt -eq 3) { throw }
            Start-Sleep -Seconds 3
        }
    }
}
$Signature = Get-AuthenticodeSignature -LiteralPath $Autologon
if ($Signature.Status -ne "Valid" -or $Signature.SignerCertificate.Subject -notmatch "Microsoft Corporation") {
    throw "Autologon's Microsoft signature could not be verified. No account or startup settings were changed."
}
$Wizard = Join-Path $PSScriptRoot "enable-unattended.ps1"
$Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$Wizard`""
$LorExe = Join-Path ${env:ProgramFiles(x86)} "Light-O-Rama\LORTray.Windows.exe"
if ((-not $SkipLightORama) -and (Test-Path -LiteralPath $LorExe)) {
    $Arguments += " -StartLightORama"
    Write-Host "Light-O-Rama is installed; its Control Panel will also start at sign-in."
} else {
    Write-Host "Configuring NUMAN and Ollama only. Rerun this setup after installing Light-O-Rama to add its task."
}
Write-Host "Approve the administrator prompt, then enter the show-account password locally when asked."
$WizardProcess = Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Verb RunAs -ArgumentList $Arguments -Wait -PassThru
if ($WizardProcess.ExitCode -ne 0) { throw "Unattended startup configuration failed (exit $($WizardProcess.ExitCode))." }
Write-Host "Startup wizard closed. Complete the first-login and reboot checks in docs\ROB-GUIDE.md."
