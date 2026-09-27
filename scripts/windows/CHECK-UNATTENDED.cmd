@echo off
powershell.exe -NoProfile -Command "Get-ScheduledTask -TaskName 'NUMAN-*' | Select-Object TaskName,State; Get-ScheduledTaskInfo -TaskName 'NUMAN-Show' | Select-Object LastRunTime,LastTaskResult; Get-Content -LiteralPath 'C:\ProgramData\NUMAN\logs\supervisor.log' -Tail 12"
pause
