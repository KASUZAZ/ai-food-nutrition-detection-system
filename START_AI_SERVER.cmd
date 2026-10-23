@echo off
setlocal
cd /d "%~dp0"
title AI Food Nutrition System - AI Server
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_ai_server.ps1"
pause
