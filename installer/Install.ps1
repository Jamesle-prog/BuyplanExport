# PO Automation GIII - Installer
# Run once on a new Windows computer to set up the app.
# Safe to re-run: skips steps that are already done (existing Python, existing venv).

$ErrorActionPreference = "Stop"
$AppDir = $PSScriptRoot
$PythonVersion = "3.13.1"
$PythonInstallerUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"

function Write-Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "    $msg" -ForegroundColor Red }

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  PO Automation GIII -- Installer" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "App folder: $AppDir"

# ---------------------------------------------------------------------------
# 1. Find or install Python 3.13
# ---------------------------------------------------------------------------
Write-Step "Checking for Python 3.13..."

function Find-Python313 {
    # Prefer the official py.exe launcher's own list -- most reliable signal.
    try {
        $pyList = & py -0p 2>$null
        foreach ($line in $pyList) {
            if ($line -match "3\.13\S*\s+(.+python\.exe)") {
                $candidate = $matches[1].Trim()
                if (Test-Path $candidate) { return $candidate }
            }
        }
    } catch {}
    # Fall back to the two most common install locations.
    $commonPaths = @(
        "$env:LocalAppData\Programs\Python\Python313\python.exe",
        "C:\Python313\python.exe"
    )
    foreach ($p in $commonPaths) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

$pythonExe = Find-Python313

if (-not $pythonExe) {
    Write-Warn "Python 3.13 not found -- downloading the official installer..."
    Write-Warn "(Source: $PythonInstallerUrl)"
    $installerPath = Join-Path $env:TEMP "python-$PythonVersion-amd64.exe"
    Invoke-WebRequest -Uri $PythonInstallerUrl -OutFile $installerPath -UseBasicParsing

    Write-Warn "Installing Python $PythonVersion for the current user (no admin rights needed)..."
    $installArgs = "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0"
    Start-Process -FilePath $installerPath -ArgumentList $installArgs -Wait
    Remove-Item $installerPath -Force -ErrorAction SilentlyContinue

    $pythonExe = Find-Python313
    if (-not $pythonExe) {
        Write-Err "Python was installed but this script can't locate it yet (PATH needs a refresh)."
        Write-Err "Close this window, open a NEW PowerShell window, and run Install.ps1 again."
        exit 1
    }
    Write-Ok "Python $PythonVersion installed."
} else {
    Write-Ok "Found existing Python 3.13 at: $pythonExe"
}

# ---------------------------------------------------------------------------
# 2. Create a virtual environment dedicated to this app
# ---------------------------------------------------------------------------
Write-Step "Setting up the app's Python environment..."

$venvDir = Join-Path $AppDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (Test-Path $venvPython) {
    Write-Ok "Virtual environment already exists -- reusing it."
} else {
    & $pythonExe -m venv $venvDir
    Write-Ok "Created virtual environment at .venv\"
}

# ---------------------------------------------------------------------------
# 3. Install dependencies (pinned, known-good versions)
# ---------------------------------------------------------------------------
Write-Step "Installing dependencies (this can take a few minutes)..."
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -r (Join-Path $AppDir "requirements.lock")
Write-Ok "Dependencies installed."

# ---------------------------------------------------------------------------
# 4. Register the license for THIS machine
# ---------------------------------------------------------------------------
Write-Step "Registering the license for this computer..."
Push-Location $AppDir
& $venvPython -m auth.generate_license
Write-Ok "License registered."

# ---------------------------------------------------------------------------
# 5. Create the first login account(s) (interactive)
# ---------------------------------------------------------------------------
Write-Step "Create your login account(s) now"
Write-Host "    (The first account you create here becomes an admin automatically.)" -ForegroundColor DarkGray
Write-Host "    (You can add or reset accounts later by re-running setup_users.py)" -ForegroundColor DarkGray
& $venvPython setup_users.py
Pop-Location

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=================================================" -ForegroundColor Green
Write-Host "  Install complete!" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Green
Write-Host "Double-click 'Start_PO_Extractor.bat' any time to launch the app."
Write-Host "To remove the app later, see 'Uninstall.bat'."
Write-Host ""
