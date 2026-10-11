$ErrorActionPreference = "Stop"

$repoArchive = "https://github.com/Gr33nOps/sonkip/archive/refs/heads/main.zip"
$installDir = Join-Path $env:LOCALAPPDATA "Sonkip"
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("sonkip-install-" + [guid]::NewGuid())
$archivePath = Join-Path $tempDir "sonkip.zip"
$extractDir = Join-Path $tempDir "source"

Write-Host ""
Write-Host "  SONKIP / LOCAL INSTALL" -ForegroundColor DarkYellow
Write-Host "  Installing to $installDir" -ForegroundColor DarkGray
Write-Host ""

$python = Get-Command py -ErrorAction SilentlyContinue
$pythonPrefix = @("-3")
if (-not $python) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    $pythonPrefix = @()
}
if (-not $python) {
    throw "Python 3.10 or newer is required. Install it from https://python.org/downloads/ and run this command again."
}

try {
    New-Item -ItemType Directory -Path $tempDir, $extractDir -Force | Out-Null
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null

    Write-Host "  [1/4] Downloading Sonkip..."
    Invoke-WebRequest -Uri $repoArchive -OutFile $archivePath -UseBasicParsing
    Expand-Archive -Path $archivePath -DestinationPath $extractDir -Force

    $sourceDir = Get-ChildItem -Path $extractDir -Directory | Select-Object -First 1
    if (-not $sourceDir) {
        throw "The downloaded Sonkip archive was empty."
    }

    Write-Host "  [2/4] Installing app files..."
    Copy-Item -Path (Join-Path $sourceDir.FullName "*") -Destination $installDir -Recurse -Force

    $venvDir = Join-Path $installDir ".venv"
    $venvPython = Join-Path $venvDir "Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Host "  [3/4] Creating private Python environment..."
        & $python.Source @pythonPrefix -m venv $venvDir
    } else {
        Write-Host "  [3/4] Reusing private Python environment..."
    }

    Write-Host "  [4/4] Installing dependencies..."
    & $venvPython -m pip install --disable-pip-version-check -r (Join-Path $installDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Python dependency installation failed."
    }

    $launcherPath = Join-Path $installDir "Start Sonkip.cmd"
    $launcher = @"
@echo off
cd /d "$installDir"
start "Sonkip" "$venvPython" "$installDir\run.py"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8000"
"@
    Set-Content -Path $launcherPath -Value $launcher -Encoding ASCII

    Write-Host ""
    Write-Host "  Sonkip is installed." -ForegroundColor Green
    Write-Host "  Launcher: $launcherPath" -ForegroundColor DarkGray
    Write-Host ""
    & $launcherPath
} finally {
    if (Test-Path $tempDir) {
        Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
