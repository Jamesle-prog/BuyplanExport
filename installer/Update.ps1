# PO Automation GIII - Updater
# Run this from a NEWLY EXTRACTED pack folder to update an EXISTING install
# in place. Copies in the new app code and refreshes dependencies, but never
# touches your PO history, fabric database, login accounts, or license --
# those only ever exist in the OLD install and are explicitly excluded below.

param(
    [string]$TargetDir
)

$ErrorActionPreference = "Stop"
$SourceDir = $PSScriptRoot

function Write-Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "    $msg" -ForegroundColor Red }

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  PO Automation GIII -- Updater" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "New pack folder: $SourceDir"

if (-not $TargetDir) {
    $TargetDir = Read-Host "Path to your EXISTING install folder (the one you want to update)"
}
$TargetDir = $TargetDir.Trim('"')

if (-not (Test-Path (Join-Path $TargetDir "app.py"))) {
    Write-Err "Doesn't look like a PO Automation GIII install (no app.py found at '$TargetDir')."
    exit 1
}
if ((Resolve-Path $TargetDir).Path -eq (Resolve-Path $SourceDir).Path) {
    Write-Err "Target is the same folder as this new pack. Point this at your OLD install instead."
    exit 1
}

$resolvedTarget = (Resolve-Path $TargetDir).Path
Write-Ok "Target install: $resolvedTarget"

# ---------------------------------------------------------------------------
# 1. Stop the app first if it's running in the target folder
# ---------------------------------------------------------------------------
Write-Step "Checking whether the app is currently running..."

$running = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*streamlit*" -and $_.CommandLine -like "*$resolvedTarget*" }

if ($running) {
    Write-Warn "The app looks like it's running (PID: $($running.ProcessId -join ', '))."
    $stop = Read-Host "    Stop it now so update can proceed? (y/N)"
    if ($stop -eq "y" -or $stop -eq "Y") {
        $running | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 1
        Write-Ok "Stopped."
    } else {
        Write-Err "Close the app first, then run this script again."
        exit 1
    }
} else {
    Write-Ok "Not running."
}

# ---------------------------------------------------------------------------
# 2. Copy the new code over the target -- explicitly never touching data,
#    accounts, or the license, regardless of whether this pack happens to
#    contain files by those names.
# ---------------------------------------------------------------------------
Write-Step "Copying updated files into $resolvedTarget ..."
Write-Host "    Never touched, no matter what: .venv\, logs\, auth\users.json," -ForegroundColor DarkGray
Write-Host "    auth\license.key, auth\smtp_settings.json, data\*.db and its -journal/-wal/-shm files" -ForegroundColor DarkGray

$robocopyArgs = @(
    $SourceDir, $resolvedTarget,
    "/E",
    "/XF", "users.json", "license.key", "smtp_settings.json", "*.db", "*.db-journal", "*.db-wal", "*.db-shm",
    "/XD", ".venv", "logs",
    "/NFL", "/NDL", "/NJH"
)
robocopy @robocopyArgs | Out-Null
$rc = $LASTEXITCODE
if ($rc -ge 8) {
    Write-Err "robocopy reported errors (exit code $rc). Nothing further was done -- check the folders manually."
    exit 1
}
Write-Ok "Files updated."

# ---------------------------------------------------------------------------
# 3. Refresh dependencies against the (possibly updated) requirements.lock
# ---------------------------------------------------------------------------
Write-Step "Refreshing dependencies..."

$venvPython = Join-Path $resolvedTarget ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    & $venvPython -m pip install -r (Join-Path $resolvedTarget "requirements.lock") --quiet
    Write-Ok "Dependencies up to date."
} else {
    Write-Warn "No .venv found in the target -- run Install.ps1 there first, then re-run this update."
}

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=================================================" -ForegroundColor Green
Write-Host "  Update complete" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Green
Write-Host "Your PO history, fabric database, accounts, and license were untouched."
Write-Host "Double-click Start_PO_Extractor.bat in the target folder to launch the updated app."
Write-Host ""
