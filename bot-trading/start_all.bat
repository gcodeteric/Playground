@echo off
title Launcher - TWS + Bot + Dashboard
cd /d "%~dp0"

echo.
echo ========================================
echo    A ARRANCAR TWS + BOT + DASHBOARD
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

rem Auto-login TWS
echo A abrir TWS e fazer login automatico...
"%~dp0venv\Scripts\python.exe" tws_autologin.py
if errorlevel 1 (
    echo.
    echo AVISO: auto-login falhou.
    echo Faz login manualmente no TWS e prime qualquer tecla para continuar.
    pause
)

echo.
echo TWS pronto. A arrancar dashboard e bot...
echo.

rem Abrir dashboard numa janela separada
start "Dashboard de Trading" cmd /k "cd /d "%~dp0" && "%~dp0venv\Scripts\python.exe" -m streamlit run dashboard/app.py --server.port 8501 --server.headless true --server.address 0.0.0.0"

rem Aguardar dashboard arrancar
timeout /t 3 /nobreak >nul

rem Abrir browser
start http://localhost:8501

rem Arrancar bot nesta janela
echo A arrancar bot...
echo.
"%~dp0venv\Scripts\python.exe" main.py
pause
