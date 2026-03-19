@echo off
title Dashboard de Trading
cd /d "%~dp0"
call venv\Scripts\activate.bat
echo.
echo ========================================
echo    DASHBOARD - A ARRANCAR...
echo ========================================
echo.
pip install streamlit plotly --quiet
streamlit run dashboard/app.py --server.port 8501 --server.headless true
pause
