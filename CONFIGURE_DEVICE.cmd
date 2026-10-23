@echo off
setlocal
cd /d "%~dp0"
title AI Food Nutrition System - Device Configuration
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_full_project.ps1" -ConfigureOnly
pause
