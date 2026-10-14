# Installs the plugin for testing, without the UXP Developer Tool or the Creative Cloud app.
# It copies the plugin into Premiere's external plugins folder under the name Premiere expects
# (<manifest id>_<manifest version>). Restart Premiere afterwards.
#
#   install-dev.bat              install / update
#   install-dev.bat -Uninstall   remove it again

param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$manifest = Get-Content (Join-Path $PSScriptRoot "manifest.json") -Raw | ConvertFrom-Json
$folderName = "$($manifest.id)_$($manifest.version)"
$external = Join-Path $env:APPDATA "Adobe\UXP\Plugins\External"
$target = Join-Path $external $folderName

# Remove any earlier copy of this plugin, whatever its version, so two versions never sit side by side.
if (Test-Path $external) {
    Get-ChildItem $external -Directory -Filter "$($manifest.id)_*" | ForEach-Object {
        Write-Host "Removing $($_.FullName)"
        Remove-Item $_.FullName -Recurse -Force
    }
}

if ($Uninstall) {
    Write-Host "Uninstalled. Restart Premiere Pro."
    exit 0
}

New-Item -ItemType Directory -Path $target -Force | Out-Null
Copy-Item (Join-Path $PSScriptRoot "manifest.json") $target
Copy-Item (Join-Path $PSScriptRoot "index.html") $target
Copy-Item (Join-Path $PSScriptRoot "src") $target -Recurse

Write-Host "Installed to $target"
if (Get-Process -Name "Adobe Premiere Pro" -ErrorAction SilentlyContinue) {
    Write-Host "Premiere Pro is running: close it and open it again to load the new version." -ForegroundColor Yellow
} else {
    Write-Host "Start Premiere Pro and look for the panel under Window > UXP Plugins / Extensions."
}
