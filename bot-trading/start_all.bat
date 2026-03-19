@echo off
title Launcher - Bot + Dashboard
cd /d "%~dp0"

echo.
echo ========================================
echo    A ARRANCAR BOT + DASHBOARD
echo ========================================
echo.

rem Apagar locks de sessoes anteriores
if exist "data\bot.instance.lock" (
    del /f "data\bot.instance.lock"
    echo Lock anterior removido.
)
for %%f in ("%TEMP%\bot-trading-instance-locks\*.lock") do (
    del /f "%%f" 2>nul
)

rem Abrir dashboard numa janela separada
echo A abrir dashboard...
start "Dashboard" cmd /k "cd /d "%~dp0" && "%~dp0venv\Scripts\python.exe" -m streamlit run dashboard/app.py --server.port 8501 --server.headless true"

rem Aguardar 3 segundos para o dashboard arrancar
timeout /t 3 /nobreak >nul

rem Abrir browser
echo A abrir browser...
start http://localhost:8501

rem Arrancar bot nesta janela
echo A arrancar bot...
echo.
"%~dp0venv\Scripts\python.exe" main.py
pause
