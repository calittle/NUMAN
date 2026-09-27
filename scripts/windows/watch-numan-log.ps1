param([string]$LogRoot = (Join-Path $env:ProgramData "NUMAN\logs"))
$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "NUMAN - Live Log"
$Mutex = New-Object System.Threading.Mutex($false, "Local\NUMAN-LogViewer")
if (-not $Mutex.WaitOne(0)) { $Mutex.Dispose(); exit 0 }
$Reader = $null
$CurrentPath = $null
try {
    Write-Host "Following NUMAN logs. Closing this window does not stop NUMAN." -ForegroundColor Cyan
    while ($true) {
        $Latest = Get-ChildItem -LiteralPath $LogRoot -Filter "numan-*.log" -File -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending | Select-Object -First 1
        if ($Latest -and $Latest.FullName -ne $CurrentPath) {
            if ($Reader) { $Reader.Dispose(); $Reader = $null }
            # Detect the UTF-16 BOM written by Windows PowerShell.
            $Stream = [System.IO.File]::Open($Latest.FullName, [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
            $Reader = New-Object System.IO.StreamReader($Stream)
            $CurrentPath = $Latest.FullName
            Write-Host "`n--- $CurrentPath ---" -ForegroundColor Cyan
        }
        if ($Reader) {
            $Text = $Reader.ReadToEnd()
            if ($Text.Length -gt 0) { Write-Host -NoNewline $Text }
        }
        Start-Sleep -Seconds 1
    }
} finally {
    if ($Reader) { $Reader.Dispose() }
    $Mutex.ReleaseMutex()
    $Mutex.Dispose()
}
