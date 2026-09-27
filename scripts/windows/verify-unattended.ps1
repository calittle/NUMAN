#Requires -RunAsAdministrator
$ErrorActionPreference = "Stop"
$OutputPath = Join-Path $env:ProgramData "NUMAN\startup-status.json"
try {
    $Tasks = @(Get-ScheduledTask -TaskName "NUMAN-Show", "NUMAN-Light-O-Rama" -ErrorAction Stop)
    if ($Tasks.Count -ne 2) { throw "Both startup tasks must exist." }
    $Winlogon = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
    $Login = Get-ItemProperty -Path $Winlogon -Name AutoAdminLogon,DefaultUserName
    if ($Login.AutoAdminLogon -ne "1" -or $Login.DefaultUserName -ne "NumanShow") { throw "Autologon is not enabled for NumanShow." }
    # Make the local-account domain explicit; never read or write stored passwords.
    Set-ItemProperty -Path $Winlogon -Name DefaultDomainName -Value $env:COMPUTERNAME
    $TaskReports = @($Tasks | ForEach-Object {
        [ordered]@{
            name = $_.TaskName
            state = [string]$_.State
            user = $_.Principal.UserId
            logon = [string]$_.Principal.LogonType
            delay = $_.Triggers.Delay
            executable = $_.Actions.Execute
            arguments = $_.Actions.Arguments
            restart_count = $_.Settings.RestartCount
            execution_limit = $_.Settings.ExecutionTimeLimit
        }
    })
    [ordered]@{
        verified_at = (Get-Date -Format o)
        autologon_enabled = $true
        account = "NumanShow"
        domain = $env:COMPUTERNAME
        tasks = $TaskReports
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
} catch {
    @{ error = $_.Exception.Message } | ConvertTo-Json | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    exit 1
}
