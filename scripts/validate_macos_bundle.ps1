$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$distRoot = Join-Path $projectRoot "dist-macos"
$appRoot = Join-Path $distRoot "BOT Suivi Shopify.app"
$requiredPaths = @(
    (Join-Path $appRoot "Contents\Info.plist"),
    (Join-Path $appRoot "Contents\MacOS\bot-suivi-shopify"),
    (Join-Path $appRoot "Contents\Resources\payload\shopify_pdf_bot_platform.py"),
    (Join-Path $appRoot "Contents\Resources\payload\requirements_shopify_pdf_bot.txt"),
    (Join-Path $distRoot "README_MAC.md")
)

$missing = @($requiredPaths | Where-Object { -not (Test-Path $_) })
if ($missing.Count -gt 0) {
    Write-Error ("Bundle macOS incomplet. Fichiers manquants:`n" + ($missing -join "`n"))
}

$plist = Get-Content (Join-Path $appRoot "Contents\Info.plist") -Raw
$launcher = Get-Content (Join-Path $appRoot "Contents\MacOS\bot-suivi-shopify") -Raw

if ($plist -notmatch "<string>bot-suivi-shopify</string>") {
    Write-Error "Info.plist invalide: executable manquant."
}

if ($launcher -notmatch "micromamba") {
    Write-Error "Launcher macOS invalide: micromamba non reference."
}

if ($launcher -notmatch "playwright install chromium") {
    Write-Error "Launcher macOS invalide: installation Playwright absente."
}

if ($launcher -notmatch "BOT_DATA_DIR") {
    Write-Error "Launcher macOS invalide: BOT_DATA_DIR absent."
}

Write-Host "Validation bundle macOS OK"
