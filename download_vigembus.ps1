$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$drivers = Join-Path $root "drivers"
$out = Join-Path $drivers "ViGEmBusSetup.exe"

New-Item -ItemType Directory -Force -Path $drivers | Out-Null

$release = Invoke-RestMethod -Uri "https://api.github.com/repos/nefarius/ViGEmBus/releases/tags/v1.22.0" -Headers @{ "User-Agent" = "SteamPadBridge" }
$asset = $release.assets | Where-Object {
    $_.name -match "\.exe$|\.msi$" -and $_.name -match "ViGEm|Setup"
} | Select-Object -First 1

if (-not $asset) {
    throw "Could not find a ViGEmBus setup asset in the v1.22.0 GitHub release."
}

Write-Host "Downloading $($asset.name)..."
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $out -UseBasicParsing
Write-Host "Saved to $out"
