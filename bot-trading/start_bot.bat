@echo off
title Bot de Trading
cd /d "%~dp0"

echo.
echo ========================================
echo    BOT DE TRADING - PAPER TRADING
echo ========================================
echo.

"%~dp0venv\Scripts\python.exe" main.py
pause
