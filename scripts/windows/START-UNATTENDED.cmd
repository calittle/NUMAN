@echo off
powershell.exe -NoProfile -Command "Start-ScheduledTask -TaskName 'NUMAN-Show' -ErrorAction Stop"
if errorlevel 1 pause
