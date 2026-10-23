[CmdletBinding()]
param(
    [switch]$ConfigureOnly,
    [switch]$SkipArduino,
    [switch]$DryRun
)

& (Join-Path $PSScriptRoot "setup_full_project.ps1") @PSBoundParameters
