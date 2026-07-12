[CmdletBinding()]
param(
    [switch]$ConfigureOnly,
    [switch]$SkipArduino,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$VenvPath = Join-Path $env:SystemDrive "food-ai-venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
$Esp32IndexUrl = "https://espressif.github.io/arduino-esp32/package_esp32_index.json"

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Invoke-Checked([string]$Program, [string[]]$Arguments, [string]$Description) {
    Write-Host "  $Description"
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

function Find-Python312 {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        & $launcher.Source -3.12 -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return [pscustomobject]@{ Path = $launcher.Source; Prefix = @("-3.12") }
        }
    }

    $candidates = @(
        (Join-Path $env:LocalAppData "Programs\Python\Python312\python.exe"),
        "C:\Program Files\Python312\python.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return [pscustomobject]@{ Path = $candidate; Prefix = @() }
        }
    }
    return $null
}

function Invoke-Python312([string[]]$Arguments, [string]$Description) {
    & $script:Python312.Path @($script:Python312.Prefix + $Arguments)
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

function Find-ArduinoCli {
    $command = Get-Command arduino-cli -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $wingetPackages = Join-Path $env:LocalAppData "Microsoft\WinGet\Packages"
    if (Test-Path -LiteralPath $wingetPackages) {
        $candidate = Get-ChildItem -Path $wingetPackages -Filter "arduino-cli.exe" -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($candidate) {
            return $candidate.FullName
        }
    }
    return $null
}

function Escape-CString([string]$Value) {
    return $Value.Replace('\', '\\').Replace('"', '\"')
}

function Get-LaptopIPv4 {
    $address = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notmatch '^(127\.|169\.254\.)' -and
            $_.InterfaceAlias -notmatch 'vEthernet|Loopback'
        } |
        Select-Object -First 1 -ExpandProperty IPAddress
    if ($address) {
        return $address
    }
    return "192.168.1.10"
}

function Write-DeviceSecrets {
    Write-Step "Device configuration"
    Write-Host "These values are saved only in local secrets.h files and are ignored by Git." -ForegroundColor Yellow
    $ssid = Read-Host "WiFi name (SSID)"
    if ([string]::IsNullOrWhiteSpace($ssid)) {
        throw "WiFi name is required. Run CONFIGURE_DEVICE.cmd again when ready."
    }

    $securePassword = Read-Host "WiFi password" -AsSecureString
    $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
    try {
        $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    }

    $defaultLaptopIp = Get-LaptopIPv4
    $laptopIp = Read-Host "Laptop IPv4 address [$defaultLaptopIp]"
    if ([string]::IsNullOrWhiteSpace($laptopIp)) {
        $laptopIp = $defaultLaptopIp
    }

    $scaleIp = Read-Host "ESP32 scale IP [192.168.1.50]"
    if ([string]::IsNullOrWhiteSpace($scaleIp)) {
        $scaleIp = "192.168.1.50"
    }
    if ($scaleIp -notmatch '^https?://') {
        $scaleUrl = "http://$scaleIp/api/food"
    }
    else {
        $scaleUrl = $scaleIp.TrimEnd('/')
    }

    $safeSsid = Escape-CString $ssid
    $safePassword = Escape-CString $password
    $safeScaleUrl = Escape-CString $scaleUrl
    $safeAiUrl = Escape-CString "http://${laptopIp}:5000/classify"

    $scaleSecrets = @"
#pragma once
#define NUTRITION_WIFI_SSID "$safeSsid"
#define NUTRITION_WIFI_PASS "$safePassword"
"@

    $cameraSecrets = @"
#pragma once
#define NUTRITION_WIFI_SSID "$safeSsid"
#define NUTRITION_WIFI_PASS "$safePassword"
#define NUTRITION_SCALE_URL "$safeScaleUrl"
#define NUTRITION_AI_SERVER_URL "$safeAiUrl"
"@

    $encoding = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText((Join-Path $ProjectRoot "arduino\esp32_scale_nutrition\secrets.h"), $scaleSecrets, $encoding)
    [IO.File]::WriteAllText((Join-Path $ProjectRoot "arduino\esp32_cam_detection_sender\secrets.h"), $cameraSecrets, $encoding)
    Write-Host "Local WiFi and IP configuration saved." -ForegroundColor Green
}

Write-Host "AI Food Nutrition System - Full Setup" -ForegroundColor Green
Write-Host "Project folder: $ProjectRoot"

if (-not (Test-Path (Join-Path $ProjectRoot "requirements-ai.txt")) -or
    -not (Test-Path (Join-Path $ProjectRoot "tools\real_ai_server.py"))) {
    throw "This setup file must remain inside the complete project folder. Extract the whole GitHub ZIP first."
}

if ($DryRun) {
    Write-Host "Dry run only. No software, model, or local secrets will be changed."
    Write-Host "Would install: Python 3.12, Arduino CLI, PyTorch/Transformers, ESP32 core, HX711, LiquidCrystal I2C."
    Write-Host "Would create: $VenvPath and local secrets.h files after asking for WiFi and IP values."
    exit 0
}

if ($ConfigureOnly) {
    Write-DeviceSecrets
    exit 0
}

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "Windows Package Manager (winget) is required. Install or update App Installer from Microsoft Store, then run START_SETUP.cmd again."
}

$script:Python312 = Find-Python312
if (-not $script:Python312) {
    Write-Step "Installing Python 3.12"
    Invoke-Checked "winget" @("install", "--id", "Python.Python.3.12", "--exact", "--source", "winget", "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity") "Install Python 3.12"
    Refresh-ProcessPath
    $script:Python312 = Find-Python312
    if (-not $script:Python312) {
        throw "Python 3.12 was installed but cannot be found in this window. Close this window and run START_SETUP.cmd once more."
    }
}

Write-Step "Preparing Python AI environment"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    Invoke-Python312 @("-m", "venv", $VenvPath) "Create Python environment"
}
Invoke-Checked $VenvPython @("-m", "pip", "install", "--upgrade", "pip") "Upgrade pip"
Invoke-Checked $VenvPython @("-m", "pip", "install", "-r", (Join-Path $ProjectRoot "requirements-ai.txt")) "Install AI packages"
Invoke-Checked $VenvPython @((Join-Path $ProjectRoot "tools\preload_ai_model.py")) "Download and validate AI model"

if (-not $SkipArduino) {
    $arduinoCli = Find-ArduinoCli
    if (-not $arduinoCli) {
        Write-Step "Installing Arduino CLI"
        Invoke-Checked "winget" @("install", "--id", "ArduinoSA.CLI", "--exact", "--source", "winget", "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity") "Install Arduino CLI"
        Refresh-ProcessPath
        $arduinoCli = Find-ArduinoCli
        if (-not $arduinoCli) {
            throw "Arduino CLI was installed but cannot be found in this window. Close this window and run START_SETUP.cmd once more."
        }
    }

    Write-Step "Preparing Arduino ESP32 toolchain"
    Invoke-Checked $arduinoCli @("core", "update-index", "--additional-urls", $Esp32IndexUrl) "Update Arduino board index"
    Invoke-Checked $arduinoCli @("core", "install", "esp32:esp32", "--additional-urls", $Esp32IndexUrl) "Install ESP32 board support"
    Invoke-Checked $arduinoCli @("lib", "install", "HX711") "Install HX711 library"
    Invoke-Checked $arduinoCli @("lib", "install", "LiquidCrystal I2C") "Install LiquidCrystal I2C library"
}

Write-DeviceSecrets

Write-Host "`nSetup complete." -ForegroundColor Green
Write-Host "1. Upload the ESP32 scale sketch."
Write-Host "2. Run CONFIGURE_DEVICE.cmd again after you know the Scale IP."
Write-Host "3. Upload the ESP32-CAM sketch."
Write-Host "4. Double-click START_AI_SERVER.cmd whenever the system is used."
