#Requires -RunAsAdministrator
param([string]$AccountName = "NumanShow", [switch]$StartLightORama)
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RuntimeRoot = Join-Path $env:ProgramData "NUMAN"
$UserId = "$env:COMPUTERNAME\$AccountName"
if (-not (Test-Path (Join-Path $RuntimeRoot "venv\Scripts\python.exe"))) { throw "Run prepare-unattended.ps1 first." }
$Account = Get-LocalUser -Name $AccountName -ErrorAction SilentlyContinue
if (-not $Account) {
    $Credential = Get-Credential -UserName $UserId -Message "Choose a password for the dedicated NUMAN show account. Use this same password in Microsoft Autologon afterward."
    if (-not $Credential) { throw "Account creation was cancelled." }
    if ($Credential.Password.Length -eq 0) { throw "A nonempty password is required." }
    $Account = New-LocalUser -Name $AccountName -Password $Credential.Password -Description "NUMAN show computer" -PasswordNeverExpires
    Add-LocalGroupMember -SID "S-1-5-32-545" -Member $Account
    $Credential = $null
}
# Standard account: read runtime/code, write models, diagnostics, compiled keywords.
& icacls $RuntimeRoot /grant "${UserId}:(OI)(CI)RX" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Runtime read permissions could not be set." }
foreach ($Writable in @((Join-Path $RuntimeRoot "logs"), (Join-Path $RuntimeRoot "models"), (Join-Path $ProjectRoot "models"))) {
    & icacls $Writable /grant "${UserId}:(OI)(CI)M" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Write permissions could not be set on $Writable." }
}
$Runner = Join-Path $PSScriptRoot "run-unattended.ps1"
$PowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$Action = New-ScheduledTaskAction -Execute $PowerShell -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Runner`"" -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserId
$Trigger.Delay = "PT30S"
$Principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "NUMAN-Show" -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description "NUMAN audio worker and Ollama supervisor in the dedicated show account." -Force | Out-Null
if ($StartLightORama) {
    $LorExe = Join-Path ${env:ProgramFiles(x86)} "Light-O-Rama\LORTray.Windows.exe"
    if (-not (Test-Path -LiteralPath $LorExe)) { throw "Light-O-Rama Control Panel was not found." }
    $LorAction = New-ScheduledTaskAction -Execute $LorExe -WorkingDirectory (Split-Path $LorExe)
    Register-ScheduledTask -TaskName "NUMAN-Light-O-Rama" -Action $LorAction -Trigger $Trigger -Principal $Principal -Settings $Settings -Description "Open the LOR Control Panel in the show account; does not configure or enable shows." -Force | Out-Null
}
# Let the standard show account inspect/start/stop its own tasks.
$Scheduler = New-Object -ComObject Schedule.Service
$Scheduler.Connect()
$TaskFolder = $Scheduler.GetFolder("\")
$TaskNames = @("NUMAN-Show")
if ($StartLightORama) { $TaskNames += "NUMAN-Light-O-Rama" }
foreach ($TaskName in $TaskNames) {
    $TaskFolder.GetTask($TaskName).SetSecurityDescriptor("D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGX;;;$($Account.SID.Value))", 0)
}
# Keep the show awake on mains power; battery and screen settings are unchanged.
& powercfg.exe /change standby-timeout-ac 0
if ($LASTEXITCODE -ne 0) { throw "Could not disable plugged-in sleep." }
Write-Host "Tasks registered for $UserId. No reboot or sign-out was performed." -ForegroundColor Green
Write-Host "In Autologon, set Username to $AccountName, Domain to $env:COMPUTERNAME, and enter the account password locally. Click Enable." -ForegroundColor Yellow
Write-Host "Then sign in to $AccountName once to finish Windows and check microphone access, speakers, and Light-O-Rama licensing."
$Autologon = Join-Path $RuntimeRoot "autologon\Autologon64.exe"
$Winlogon = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
$ExistingLogin = Get-ItemProperty -Path $Winlogon -Name AutoAdminLogon,DefaultUserName -ErrorAction SilentlyContinue
if ($ExistingLogin.AutoAdminLogon -eq "1" -and $ExistingLogin.DefaultUserName -eq $AccountName) {
    Set-ItemProperty -Path $Winlogon -Name DefaultDomainName -Value $env:COMPUTERNAME
    Write-Host "Automatic login is already enabled for $UserId; preserving its password." -ForegroundColor Green
} elseif (Test-Path -LiteralPath $Autologon) {
    Start-Process -FilePath $Autologon -Wait
    $Winlogon = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
    $Login = Get-ItemProperty -Path $Winlogon -Name AutoAdminLogon,DefaultUserName -ErrorAction SilentlyContinue
    if ($Login.AutoAdminLogon -eq "1" -and $Login.DefaultUserName -eq $AccountName) {
        Set-ItemProperty -Path $Winlogon -Name DefaultDomainName -Value $env:COMPUTERNAME
        Write-Host "Automatic login is enabled for $UserId." -ForegroundColor Green
    } else {
        Write-Warning "Automatic login is not yet enabled for $AccountName. Complete it in Microsoft Autologon before relying on unattended startup."
    }
} else {
    Write-Host "Get Microsoft Autologon: https://learn.microsoft.com/en-us/sysinternals/downloads/autologon"
}
Read-Host "Press Enter to close"
