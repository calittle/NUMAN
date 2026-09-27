@echo off
title NUMAN Update
cd /d "%~dp0\..\.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0update-numan.ps1"
echo.
pause
