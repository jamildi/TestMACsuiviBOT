$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$bundleRoot = Join-Path $projectRoot "dist-windows\BOT Suivi Shopify"
$launcherPath = Join-Path $bundleRoot "BOT Suivi Shopify.cmd"
$iconPath = Join-Path $bundleRoot "BOT Suivi Shopify.ico"
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "BOT Suivi Shopify.lnk"

if (-not (Test-Path $launcherPath)) {
    throw "Lanceur Windows introuvable. Generez d'abord le bundle avec build_windows_bundle.ps1."
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcherPath
$shortcut.WorkingDirectory = $bundleRoot
$shortcut.IconLocation = $iconPath
$shortcut.Description = "BOT Suivi Shopify"
$shortcut.Save()

Write-Host "Raccourci cree sur le Bureau: $shortcutPath"
