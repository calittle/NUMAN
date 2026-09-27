@echo off
title NUMAN Unattended Startup Setup
cd /d "%~dp0\..\.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure-unattended.ps1" %*
echo.
pause
