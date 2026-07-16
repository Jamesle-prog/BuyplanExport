# PO Automation GIII - Build a self-contained install pack (dev-machine tool)
#
# Run this on the DEV machine to produce a single zip you can copy to a
# DIFFERENT PC and install from there (no git, no source checkout needed on
# the target machine -- see INSTALL_README.md, which travels inside the pack).
#
# Why this exists: Install.ps1 / Update.ps1 / Uninstall.ps1 all resolve
# their own paths as `$AppDir = $PSScriptRoot` -- they expect requirements.lock,
# setup_users.py, app.py, auth/, data/, po_extractor/, ui/ to be DIRECT
# SIBLINGS of themselves. In this dev repo they live one level down, under
# installer/, so a pack that just zipped the repo as-is would put them a
# folder too deep and every path those scripts touch would silently miss.
# This script exports the tracked tree via `git archive` (so the pack is
# clean by construction -- no .venv, no data/*.db, no local users.json/
# license.key, no __pycache__, no untracked scratch files: none of that
# was ever committed, so git archive never sees it) and then flattens
# installer/*'s contents up to the pack's root before zipping.

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "    $msg" -ForegroundColor Red }

$RepoRoot = (git rev-parse --show-toplevel 2>$null)
if (-not $RepoRoot) {
    Write-Err "Not inside a git repository -- run this from within the PO_Automation_GIII checkout."
    exit 1
}
$RepoRoot = $RepoRoot.Trim() -replace '/', '\'
Push-Location $RepoRoot

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  PO Automation GIII -- Build Install Pack" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# 1. Read the app version (for the output filename) and warn on dirty tree
# ---------------------------------------------------------------------------
Write-Step "Reading app version..."
$version = "unknown"
$appPyLine = Get-Content (Join-Path $RepoRoot "app.py") |
    Where-Object { $_ -match '^APP_VERSION\s*=\s*"([^"]+)"' } | Select-Object -First 1
if ($appPyLine -match '"([^"]+)"') { $version = $matches[1] }
Write-Ok "App version: $version"

$dirty = git status --porcelain --untracked-files=no
if ($dirty) {
    Write-Warn "You have uncommitted changes to tracked files:"
    $dirty -split "`n" | Where-Object { $_ } | ForEach-Object { Write-Warn "  $_" }
    Write-Warn "The pack is built from the last COMMIT (git archive) -- none of the above"
    Write-Warn "will be included. Commit first if you want them in the pack."
    $proceed = Read-Host "    Continue anyway? [y/N]"
    if ($proceed -notmatch '^[Yy]') {
        Write-Host "Aborted."
        Pop-Location
        exit 1
    }
}

# ---------------------------------------------------------------------------
# 2. Export the tracked tree via git archive
# ---------------------------------------------------------------------------
Write-Step "Exporting tracked files from git HEAD..."
$token = [guid]::NewGuid().ToString("N").Substring(0, 8)
$stagingDir  = Join-Path $env:TEMP "po_giii_pack_staging_$token"
$archiveZip  = Join-Path $env:TEMP "po_giii_archive_$token.zip"
New-Item -ItemType Directory -Path $stagingDir | Out-Null

# Exclude this build tool itself -- an end-user pack has no use for "build
# another pack from this pack".
git archive --format=zip -o $archiveZip HEAD -- `
    "." `
    ":!installer/Build-DistPackage.ps1" `
    ":!installer/Build-DistPackage.bat"
if ($LASTEXITCODE -ne 0) {
    Write-Err "git archive failed (exit code $LASTEXITCODE)."
    Pop-Location
    exit 1
}
Expand-Archive -Path $archiveZip -DestinationPath $stagingDir -Force
Remove-Item $archiveZip -Force
$fileCount = (Get-ChildItem $stagingDir -Recurse -File).Count
Write-Ok "Exported $fileCount files."

# ---------------------------------------------------------------------------
# 3. Flatten installer/*'s contents up to the pack root
# ---------------------------------------------------------------------------
Write-Step "Flattening installer/ scripts to the pack root..."
$installerSrc = Join-Path $stagingDir "installer"
if (Test-Path $installerSrc) {
    $movedNames = @()
    Get-ChildItem $installerSrc -File | ForEach-Object {
        Move-Item $_.FullName (Join-Path $stagingDir $_.Name) -Force
        $movedNames += $_.Name
    }
    Remove-Item $installerSrc -Recurse -Force
    Write-Ok ("Moved to pack root: " + ($movedNames -join ", "))
} else {
    Write-Err "installer/ folder not found in the archived tree -- nothing to flatten (unexpected)."
    Pop-Location
    exit 1
}

# ---------------------------------------------------------------------------
# 4. Zip the staged pack
# ---------------------------------------------------------------------------
Write-Step "Creating the distributable zip..."
$outDir = Join-Path $RepoRoot "dist"
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
$stamp  = Get-Date -Format "yyyyMMdd"
$outZip = Join-Path $outDir "PO_Automation_GIII_v${version}_${stamp}.zip"
if (Test-Path $outZip) { Remove-Item $outZip -Force }
Compress-Archive -Path (Join-Path $stagingDir "*") -DestinationPath $outZip
Remove-Item $stagingDir -Recurse -Force

$sizeMb = [math]::Round((Get-Item $outZip).Length / 1MB, 1)
Write-Ok "Created $outZip ($sizeMb MB)"

Pop-Location

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "=================================================" -ForegroundColor Green
Write-Host "  Pack built!" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Green
Write-Host "  $outZip"
Write-Host ""
Write-Host "To install on a different PC:"
Write-Host "  1. Copy this zip to the target computer (network share, USB, email, etc.)"
Write-Host "  2. Extract it anywhere (e.g. C:\Apps\PO_Automation_GIII)"
Write-Host "  3. Double-click Install.bat inside the extracted folder"
Write-Host "     (needs internet access on the target PC -- it downloads Python"
Write-Host "      if missing and installs pinned dependencies from requirements.lock)"
Write-Host "  Full instructions travel with the pack: INSTALL_README.md"
Write-Host ""
