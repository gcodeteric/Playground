@echo off
title Dashboard de Trading
cd /d "%~dp0"

echo.
echo ========================================
echo    DASHBOARD - A ARRANCAR...
echo ========================================
echo.

"%~dp0venv\Scripts\python.exe" -m streamlit run dashboard/app.py --server.port 8501 --server.headless true
pause
