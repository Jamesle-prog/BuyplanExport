@echo off
REM Double-click this file (dev machine only) to build a self-contained
REM install pack zip in dist\ -- copy that zip to a different PC to install.
REM (It just runs Build-DistPackage.ps1 with PowerShell, bypassing the
REM  "scripts are disabled" prompt that would otherwise block double-clicking
REM  a .ps1 file.)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-DistPackage.ps1"
echo.
pause
