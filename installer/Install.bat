@echo off
REM Double-click this file to install PO Automation GIII.
REM (It just runs Install.ps1 with PowerShell, bypassing the "scripts are
REM  disabled" prompt that would otherwise block double-clicking a .ps1 file.)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install.ps1"
echo.
pause
