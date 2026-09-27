@echo off
powershell.exe -NoProfile -Command "Stop-ScheduledTask -TaskName 'NUMAN-Show' -ErrorAction Stop"
if errorlevel 1 pause
