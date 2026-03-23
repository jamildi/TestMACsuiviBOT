$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$templateRoot = Join-Path $projectRoot "packaging\macos"
$distRoot = Join-Path $projectRoot "dist-macos"
$appRoot = Join-Path $distRoot "BOT Suivi Shopify.app"
$contentsRoot = Join-Path $appRoot "Contents"
$macOsRoot = Join-Path $contentsRoot "MacOS"
$resourcesRoot = Join-Path $contentsRoot "Resources"
$payloadRoot = Join-Path $resourcesRoot "payload"

if (Test-Path $appRoot) {
    Remove-Item $appRoot -Recurse -Force
}

New-Item -ItemType Directory -Path $macOsRoot -Force | Out-Null
New-Item -ItemType Directory -Path $payloadRoot -Force | Out-Null

Copy-Item (Join-Path $templateRoot "Info.plist") (Join-Path $contentsRoot "Info.plist")
Copy-Item (Join-Path $templateRoot "bot-suivi-shopify") (Join-Path $macOsRoot "bot-suivi-shopify")
Copy-Item (Join-Path $projectRoot "shopify_pdf_bot_platform.py") (Join-Path $payloadRoot "shopify_pdf_bot_platform.py")
Copy-Item (Join-Path $projectRoot "requirements_shopify_pdf_bot.txt") (Join-Path $payloadRoot "requirements_shopify_pdf_bot.txt")
Copy-Item (Join-Path $templateRoot "README_MAC.md") (Join-Path $distRoot "README_MAC.md")

Write-Host "Bundle macOS genere dans: $appRoot"
