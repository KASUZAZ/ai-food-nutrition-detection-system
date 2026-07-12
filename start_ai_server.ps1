# Starts the real food AI server after setup_new_laptop.ps1 has completed.

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$VenvPython = Join-Path (Join-Path $env:SystemDrive "food-ai-venv") "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "AI environment not found. Run .\setup_new_laptop.ps1 first."
}

Write-Host "Starting AI server ..." -ForegroundColor Green
Write-Host "Keep this PowerShell window open while the ESP32-CAM is being used."
& $VenvPython (Join-Path $ProjectRoot "tools\real_ai_server.py")
