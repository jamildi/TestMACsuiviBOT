$ErrorActionPreference = "Stop"

$AppName = "BOT Suivi Shopify"
$SupportDir = if ($env:BOT_SUPPORT_DIR) { $env:BOT_SUPPORT_DIR } else { Join-Path $env:LOCALAPPDATA $AppName }
$RuntimeDir = Join-Path $SupportDir "runtime"
$DataDir = Join-Path $SupportDir "data"
$LogDir = Join-Path $SupportDir "logs"
$PythonDir = Join-Path $SupportDir "python"
$PythonExe = Join-Path $PythonDir "python.exe"
$BrowserDir = Join-Path $SupportDir "playwright-browsers"
$MarkerFile = Join-Path $SupportDir "install.sha256"
$ServerLog = Join-Path $LogDir "server.log"
$PayloadDir = Join-Path $PSScriptRoot "payload"
$Port = if ($env:BOT_PORT) { $env:BOT_PORT } else { "5000" }
$NoOpen = $env:BOT_NO_OPEN -eq "1"

function Write-Status([string]$Message) {
    Write-Host "[$AppName] $Message"
}

function Ensure-Directories {
    @($SupportDir, $DataDir, $LogDir, $BrowserDir) | ForEach-Object {
        if (-not (Test-Path $_)) {
            New-Item -ItemType Directory -Path $_ | Out-Null
        }
    }
}

function Sync-Payload {
    $tmpDir = Join-Path $SupportDir "runtime.tmp"
    if (Test-Path $tmpDir) {
        Remove-Item $tmpDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $tmpDir | Out-Null
    Copy-Item -Path (Join-Path $PayloadDir "*") -Destination $tmpDir -Recurse -Force
    if (Test-Path $RuntimeDir) {
        Remove-Item $RuntimeDir -Recurse -Force
    }
    Move-Item -Path $tmpDir -Destination $RuntimeDir
}

function Ensure-Python {
    if (Test-Path $PythonExe) {
        return
    }

    $version = "3.11.9"
    $zipUrl = "https://www.python.org/ftp/python/$version/python-$version-embed-amd64.zip"
    $zipPath = Join-Path $env:TEMP "python-embed-$version.zip"
    $pipPath = Join-Path $env:TEMP "get-pip.py"

    Write-Status "Telechargement de Python embarque..."
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath

    if (Test-Path $PythonDir) {
        Remove-Item $PythonDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $PythonDir | Out-Null
    Expand-Archive -Path $zipPath -DestinationPath $PythonDir -Force

    $pthFile = Get-ChildItem -Path $PythonDir -Filter "python*._pth" | Select-Object -First 1
    if (-not $pthFile) {
        throw "Fichier ._pth Python introuvable."
    }

    @(
        "python311.zip"
        "."
        "Lib"
        "Lib\site-packages"
        "import site"
    ) | Set-Content -Path $pthFile.FullName -Encoding ASCII

    Write-Status "Installation de pip..."
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $pipPath
    & $PythonExe $pipPath --no-warn-script-location | Out-Host
}

function Get-StateHash {
    $items = @(
        (Get-FileHash (Join-Path $RuntimeDir "requirements_shopify_pdf_bot.txt") -Algorithm SHA256).Hash
        (Get-FileHash (Join-Path $RuntimeDir "shopify_pdf_bot_platform.py") -Algorithm SHA256).Hash
    ) -join ""
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($items)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

function Install-Dependencies {
    $stateHash = Get-StateHash
    $currentHash = if (Test-Path $MarkerFile) { (Get-Content $MarkerFile -Raw).Trim() } else { "" }
    if ($currentHash -eq $stateHash) {
        return
    }

    Write-Status "Installation des dependances Python..."
    & $PythonExe -m pip install --upgrade pip | Out-Host
    & $PythonExe -m pip install -r (Join-Path $RuntimeDir "requirements_shopify_pdf_bot.txt") | Out-Host

    Write-Status "Installation de Chromium pour Playwright..."
    $env:PLAYWRIGHT_BROWSERS_PATH = $BrowserDir
    & $PythonExe -m playwright install chromium | Out-Host

    Set-Content -Path $MarkerFile -Value $stateHash -Encoding ASCII
}

function Open-Url([string]$Url) {
    if ($NoOpen) {
        Write-Status "URL_READY=$Url"
        return
    }
    Start-Process $Url | Out-Null
}

function Test-Server {
    try {
        $response = Invoke-WebRequest -Uri ("http://127.0.0.1:{0}/" -f $Port) -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Start-Server {
    if (Test-Server) {
        Open-Url ("http://127.0.0.1:{0}/" -f $Port)
        return
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "cmd.exe"
    $scriptPath = Join-Path $RuntimeDir "shopify_pdf_bot_platform.py"
    $command = 'set "BOT_DATA_DIR={0}" && set "PLAYWRIGHT_BROWSERS_PATH={1}" && set "BOT_PORT={2}" && "{3}" "{4}" >> "{5}" 2>&1' -f `
        $DataDir, $BrowserDir, $Port, $PythonExe, $scriptPath, $ServerLog
    $psi.Arguments = "/c $command"
    $psi.WorkingDirectory = $RuntimeDir
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    [System.Diagnostics.Process]::Start($psi) | Out-Null

    for ($i = 0; $i -lt 90; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Server) {
            Open-Url ("http://127.0.0.1:{0}/" -f $Port)
            return
        }
    }

    throw "Le serveur local ne demarre pas. Consultez le log: $ServerLog"
}

try {
    Ensure-Directories
    Sync-Payload
    Ensure-Python
    Install-Dependencies
    Start-Server
} catch {
    $message = $_.Exception.Message
    Write-Error $message
    exit 1
}
