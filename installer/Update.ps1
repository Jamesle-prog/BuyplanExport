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

# Match on ExecutablePath, not just CommandLine -- Start_PO_Extractor.bat
# launches ".venv\Scripts\python.exe" via a RELATIVE path, so the command
# line never contains the install folder; the executable path always does.
$running = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
    Where-Object {
        ($_.ExecutablePath -and $_.ExecutablePath -like "$resolvedTarget\*") -or
        ($_.CommandLine -and $_.CommandLine -like "*$resolvedTarget*")
    }

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
# 2. Snapshot the databases before anything else.
#
#    This updater never writes to data\ -- but the APP does, the first time it
#    opens a database after an upgrade that adds or changes a table. Those
#    migrations run automatically at startup and some of them rewrite rows, so
#    this is the last moment at which the pre-update state can still be
#    captured. Copies only; the live files are left exactly where they are.
# ---------------------------------------------------------------------------
Write-Step "Backing up databases before the update..."

$dataDir = Join-Path $resolvedTarget "data"
$dbFiles = @()
if (Test-Path $dataDir) {
    $dbFiles = @(Get-ChildItem $dataDir -Filter "*.db" -File -ErrorAction SilentlyContinue)
}
if ($dbFiles.Count -eq 0) {
    Write-Ok "No databases found yet -- nothing to back up."
} else {
    $backupDir = Join-Path $dataDir ("backup_before_update_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
    try {
        New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
        foreach ($db in $dbFiles) {
            # -wal / -shm too: a database stopped mid-write keeps committed
            # transactions in the WAL, so the .db alone can be an older state.
            Copy-Item $db.FullName $backupDir -Force
            foreach ($side in @("-wal", "-shm")) {
                $extra = "$($db.FullName)$side"
                if (Test-Path $extra) { Copy-Item $extra $backupDir -Force }
            }
            Write-Ok "Backed up $($db.Name)"
        }
        Write-Ok "Saved to: $backupDir"
    } catch {
        Write-Warn "Could not write the backup: $($_.Exception.Message)"
        Write-Warn "Copy the 'data' folder somewhere safe yourself before continuing."
        $go = Read-Host "    Continue without a backup? (y/N)"
        if ($go -ne "y" -and $go -ne "Y") {
            Write-Err "Stopped. Nothing was changed."
            exit 1
        }
    }
}

# ---------------------------------------------------------------------------
# 3. Copy the new code over the target -- explicitly never touching data,
#    accounts, or the license, regardless of whether this pack happens to
#    contain files by those names.
#
#    The data\ directories are excluded WHOLESALE (not file-by-file): besides
#    the SQLite DBs they hold files the app edits at runtime through its admin
#    screens -- companies, size order, output schema, custom fibers, and the
#    buy-plan template workbooks -- all of which also ship in the pack with
#    factory defaults. A file-by-file exclude list would clobber the user's
#    live edits the first time a new runtime-editable file was forgotten here.
#    (Template layout updates are delivered through Admin > Templates instead.)
# ---------------------------------------------------------------------------
Write-Step "Copying updated files into $resolvedTarget ..."
Write-Host "    Never touched, no matter what: .venv\, logs\, data\ (databases," -ForegroundColor DarkGray
Write-Host "    templates, size order, schema, custom fibers), auth\users.json," -ForegroundColor DarkGray
Write-Host "    auth\license.key, auth\companies.json, auth\smtp_settings.json" -ForegroundColor DarkGray

$robocopyArgs = @(
    $SourceDir, $resolvedTarget,
    "/E",
    "/XF", "users.json", "license.key", "smtp_settings.json", "companies.json",
           "*.db", "*.db-journal", "*.db-wal", "*.db-shm",
    "/XD", ".venv", "logs", "data",
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
# 4. Refresh dependencies against the (possibly updated) requirements.lock
# ---------------------------------------------------------------------------
Write-Step "Refreshing dependencies..."

$venvPython = Join-Path $resolvedTarget ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    & $venvPython -m pip install -r (Join-Path $resolvedTarget "requirements.lock") --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Err "pip failed (exit code $LASTEXITCODE) -- the new code is in place but its"
        Write-Err "dependencies may be missing. Check your internet connection and re-run"
        Write-Err "this update; it's safe to run repeatedly."
        exit 1
    }
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
if ($backupDir -and (Test-Path $backupDir)) {
    Write-Host "A copy of the databases as they were before this update is in:"
    Write-Host "  $backupDir" -ForegroundColor DarkGray
    Write-Host "Delete it once the updated app has run normally for a day or two."
}
Write-Host "Double-click Start_PO_Extractor.bat in the target folder to launch the updated app."
Write-Host ""
