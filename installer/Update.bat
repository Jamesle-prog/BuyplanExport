@echo off
REM Run this from a NEWLY EXTRACTED pack folder to update an EXISTING install
REM in place. It will ask for the path to your existing install folder.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Update.ps1"
echo.
pause
