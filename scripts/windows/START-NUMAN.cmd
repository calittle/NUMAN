@echo off
title NUMAN - Captain Grog and Polly
cd /d "%~dp0\..\.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-numan.ps1"
if errorlevel 1 pause
