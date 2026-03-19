@echo off
title Launcher - Bot + Dashboard
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

rem Arrancar TWS
echo A abrir TWS...
set TWS_PATH=C:\Jts\tws.exe
if not exist "%TWS_PATH%" set TWS_PATH=%USERPROFILE%\Jts\tws.exe
if not exist "%TWS_PATH%" set TWS_PATH=C:\Program Files\IB TWS\tws.exe
if exist "%TWS_PATH%" (
    start "" "%TWS_PATH%"
    echo TWS a arrancar — aguardar 30 segundos para login...
    timeout /t 30 /nobreak
) else (
    echo AVISO: TWS nao encontrado no caminho esperado.
    echo Abre o TWS manualmente e prime qualquer tecla para continuar.
    pause
)

rem Abrir dashboard numa janela separada
echo A abrir dashboard...
start "Dashboard" cmd /k "cd /d "%~dp0" && "%~dp0venv\Scripts\python.exe" -m streamlit run dashboard/app.py --server.port 8501 --server.headless true --server.address 0.0.0.0"

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
