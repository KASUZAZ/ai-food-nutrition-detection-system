@echo off
setlocal
cd /d "%~dp0"
title AI Food Nutrition System - Full Setup
echo.
echo Starting full project setup. Keep this window open until complete.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_full_project.ps1"
echo.
if errorlevel 1 (
  echo Setup stopped. Read the error above, fix it, then run START_SETUP.cmd again.
) else (
  echo Setup complete. Next, upload both Arduino sketches and run START_AI_SERVER.cmd.
)
pause
