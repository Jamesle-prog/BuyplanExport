# PO Automation GIII - Uninstaller
# Removes what Install.ps1 set up. Safe by default: your PO history, fabric
# database, and login accounts are kept unless you explicitly ask to erase them.

$ErrorActionPreference = "Stop"
$AppDir = $PSScriptRoot

function Write-Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "    $msg" -ForegroundColor Red }

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  PO Automation GIII -- Uninstaller" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "App folder: $AppDir"

# ---------------------------------------------------------------------------
# 1. Stop the app first if it's running -- otherwise its files are locked
# ---------------------------------------------------------------------------
Write-Step "Checking whether the app is currently running..."

$running = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*streamlit*" -and $_.CommandLine -like "*$AppDir*" }

if ($running) {
    Write-Warn "The app looks like it's running right now (PID: $($running.ProcessId -join ', '))."
    $stop = Read-Host "    Stop it now so uninstall can proceed? (y/N)"
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
# 2. Ask what to do about data -- this is the only irreversible part
# ---------------------------------------------------------------------------
Write-Step "What should happen to your data?"
Write-Host "    This will ALWAYS remove the Python environment (.venv) and this"
Write-Host "    computer's license (auth\license.key). Both are safely rebuilt"
Write-Host "    any time by running Install.ps1 again."
Write-Host ""
Write-Host "    Your PO history, fabric database, and login accounts only exist" -ForegroundColor Yellow
Write-Host "    on this computer (auth\users.json and the data\ folder) -- they" -ForegroundColor Yellow
Write-Host "    are NOT part of the app itself and can't be recreated by reinstalling." -ForegroundColor Yellow
Write-Host ""
$confirm = Read-Host "    Type DELETE to permanently erase that data too, or press Enter to keep it"

# ---------------------------------------------------------------------------
# 3. Remove the always-safe, always-rebuildable stuff
# ---------------------------------------------------------------------------
Write-Step "Removing the Python environment and license..."

$venvDir = Join-Path $AppDir ".venv"
if (Test-Path $venvDir) {
    Remove-Item $venvDir -Recurse -Force
    Write-Ok "Removed .venv\"
} else {
    Write-Ok ".venv\ not present -- nothing to do."
}

$licenseFile = Join-Path $AppDir "auth\license.key"
if (Test-Path $licenseFile) {
    Remove-Item $licenseFile -Force
    Write-Ok "Removed auth\license.key"
} else {
    Write-Ok "auth\license.key not present -- nothing to do."
}

# ---------------------------------------------------------------------------
# 4. Only if explicitly confirmed: erase data + login accounts
# ---------------------------------------------------------------------------
if ($confirm -eq "DELETE") {
    Write-Step "Erasing data and login accounts (confirmed)..."

    $usersFile = Join-Path $AppDir "auth\users.json"
    if (Test-Path $usersFile) {
        Remove-Item $usersFile -Force
        Write-Ok "Removed auth\users.json (all login accounts)"
    }

    $dataDir = Join-Path $AppDir "data"
    if (Test-Path $dataDir) {
        Remove-Item $dataDir -Recurse -Force
        Write-Ok "Removed data\ (PO history, fabric database, generated exports)"
    }

    $logsDir = Join-Path $AppDir "logs"
    if (Test-Path $logsDir) {
        Remove-Item $logsDir -Recurse -Force
        Write-Ok "Removed logs\"
    }
} else {
    Write-Step "Keeping your data"
    Write-Ok "auth\users.json and data\ were left untouched."
}

# ---------------------------------------------------------------------------
# Done -- two things this script deliberately leaves for you to do by hand
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=================================================" -ForegroundColor Green
Write-Host "  Uninstall step complete" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Green
Write-Host ""
Write-Host "This script does NOT do two things, on purpose:"
Write-Host ""
Write-Host "  1. Delete this folder itself"
Write-Host "     ($AppDir)"
Write-Host "     It can't safely delete the files it's currently running from."
Write-Host "     Close this window, then delete the folder yourself in Explorer."
Write-Host ""
Write-Host "  2. Uninstall Python 3.13"
Write-Host "     Install.ps1 may have installed this system-wide for your Windows"
Write-Host "     account. It's left in place in case anything else on this PC"
Write-Host "     needs it. To remove it yourself: Windows Settings > Apps >"
Write-Host "     Installed apps > search 'Python 3.13' > Uninstall."
Write-Host ""
