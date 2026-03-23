$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$templateRoot = Join-Path $projectRoot "packaging\windows"
$distRoot = Join-Path $projectRoot "dist-windows"
$bundleRoot = Join-Path $distRoot "BOT Suivi Shopify"
$payloadRoot = Join-Path $bundleRoot "payload"
$iconPath = Join-Path $bundleRoot "BOT Suivi Shopify.ico"

function New-BotIcon {
    param([string]$OutputPath)

    Add-Type -AssemblyName System.Drawing

    $bmp = New-Object System.Drawing.Bitmap 256, 256
    $graphics = [System.Drawing.Graphics]::FromImage($bmp)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.Clear([System.Drawing.Color]::FromArgb(245, 247, 250))

    $rect = New-Object System.Drawing.Rectangle 18, 18, 220, 220
    $bg = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(29, 122, 98))
    $accent = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::White)
    $font = New-Object System.Drawing.Font("Segoe UI", 112, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
    $format = New-Object System.Drawing.StringFormat
    $format.Alignment = [System.Drawing.StringAlignment]::Center
    $format.LineAlignment = [System.Drawing.StringAlignment]::Center

    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $radius = 42
    $diameter = $radius * 2
    $path.AddArc($rect.X, $rect.Y, $diameter, $diameter, 180, 90)
    $path.AddArc($rect.Right - $diameter, $rect.Y, $diameter, $diameter, 270, 90)
    $path.AddArc($rect.Right - $diameter, $rect.Bottom - $diameter, $diameter, $diameter, 0, 90)
    $path.AddArc($rect.X, $rect.Bottom - $diameter, $diameter, $diameter, 90, 90)
    $path.CloseFigure()

    $graphics.FillPath($bg, $path)
    $rectF = New-Object System.Drawing.RectangleF($rect.X, $rect.Y, $rect.Width, $rect.Height)
    $graphics.DrawString("S", $font, $accent, $rectF, $format)

    $pngStream = New-Object System.IO.MemoryStream
    $bmp.Save($pngStream, [System.Drawing.Imaging.ImageFormat]::Png)
    $pngBytes = $pngStream.ToArray()

    $iconStream = New-Object System.IO.MemoryStream
    $writer = New-Object System.IO.BinaryWriter($iconStream)
    $writer.Write([UInt16]0)
    $writer.Write([UInt16]1)
    $writer.Write([UInt16]1)
    $writer.Write([Byte]0)
    $writer.Write([Byte]0)
    $writer.Write([Byte]0)
    $writer.Write([Byte]0)
    $writer.Write([UInt16]1)
    $writer.Write([UInt16]32)
    $writer.Write([UInt32]$pngBytes.Length)
    $writer.Write([UInt32]22)
    $writer.Write($pngBytes)
    [System.IO.File]::WriteAllBytes($OutputPath, $iconStream.ToArray())

    $writer.Dispose()
    $iconStream.Dispose()
    $pngStream.Dispose()
    $graphics.Dispose()
    $bmp.Dispose()
    $bg.Dispose()
    $accent.Dispose()
    $font.Dispose()
    $format.Dispose()
    $path.Dispose()
}

if (Test-Path $bundleRoot) {
    Remove-Item $bundleRoot -Recurse -Force
}

New-Item -ItemType Directory -Path $bundleRoot -Force | Out-Null
New-Item -ItemType Directory -Path $payloadRoot -Force | Out-Null

Copy-Item (Join-Path $templateRoot "BOT Suivi Shopify.cmd") (Join-Path $bundleRoot "BOT Suivi Shopify.cmd")
Copy-Item (Join-Path $templateRoot "bootstrap.ps1") (Join-Path $bundleRoot "bootstrap.ps1")
Copy-Item (Join-Path $templateRoot "README_WINDOWS.md") (Join-Path $bundleRoot "README_WINDOWS.md")
Copy-Item (Join-Path $projectRoot "shopify_pdf_bot_platform.py") (Join-Path $payloadRoot "shopify_pdf_bot_platform.py")
Copy-Item (Join-Path $projectRoot "requirements_shopify_pdf_bot.txt") (Join-Path $payloadRoot "requirements_shopify_pdf_bot.txt")

New-BotIcon -OutputPath $iconPath

Write-Host "Bundle Windows genere dans: $bundleRoot"
