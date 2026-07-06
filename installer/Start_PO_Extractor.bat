@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo App is not installed yet. Double-click Install.bat first.
    pause
    exit /b 1
)

echo Starting PO Automation GIII...
echo.
echo Once you see "You can now view your Streamlit app" below,
echo open this address in your browser:
echo.
echo     http://localhost:8501
echo.
echo Close this window to stop the app.
echo.
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless true
