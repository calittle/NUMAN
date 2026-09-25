@echo off
title NUMAN Check
cd /d "%~dp0\..\.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0check-numan.ps1"
