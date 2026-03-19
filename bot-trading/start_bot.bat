@echo off
title Bot de Trading
cd /d "%~dp0"
call venv\Scripts\activate.bat
echo.
echo ========================================
echo    BOT DE TRADING - PAPER TRADING
echo ========================================
echo.
python main.py
pause
