# Starts the unified website and AI server after setup_new_laptop.ps1.
param(
    [string]$ScaleUrl = "",
    [switch]$WebOnly,
    [switch]$NoCloud,
    [string]$CloudConfig = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$VenvPython = Join-Path (Join-Path $env:SystemDrive "food-ai-venv") "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "AI environment not found. Run .\setup_new_laptop.ps1 first."
}

Write-Host "Starting nutrition website ..." -ForegroundColor Green
Write-Host "Keep this PowerShell window open while the ESP32-CAM is being used."
$ServerArgs = @((Join-Path $ProjectRoot "tools\real_ai_server.py"))
if ($ScaleUrl) { $ServerArgs += @("--scale-url", $ScaleUrl) }
if ($WebOnly) { $ServerArgs += "--web-only" }
if ($NoCloud) { $ServerArgs += "--no-cloud" }
if ($CloudConfig) { $ServerArgs += @("--cloud-config", $CloudConfig) }
& $VenvPython @ServerArgs
