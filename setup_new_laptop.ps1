# One-time setup for a new Windows laptop.
# Requires the Python 3.12 (64-bit) launcher command: py -3.12

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$VenvPath = Join-Path $env:SystemDrive "food-ai-venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"

Write-Host "AI Food Nutrition System - New Laptop Setup" -ForegroundColor Green
Write-Host "Project folder: $ProjectRoot"

& py -3.12 --version
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.12 was not found. Install Python 3.12 (64-bit), then run this script again."
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "Creating Python environment at $VenvPath ..."
    & py -3.12 -m venv $VenvPath
}

Write-Host "Installing AI packages. This may take several minutes ..."
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $ProjectRoot "requirements-ai.txt")

Write-Host "Checking installation ..."
& $VenvPython -c "import torch, transformers, PIL; print('PyTorch', torch.__version__); print('Transformers', transformers.__version__); print('Pillow', PIL.__version__)"

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Next: run .\start_ai_server.ps1 from this project folder."
