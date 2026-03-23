@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Launcher - TWS + Bot + Dashboard
cd /d "%~dp0"

set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
set "TWS_EXE=C:\Jts\tws.exe"
set "TWS_PROCESS=tws.exe"
set "TWS_WAIT_TIMEOUT=60"

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

if not exist "%PYTHON_EXE%" (
    echo ERRO: Python do projeto nao encontrado: "%PYTHON_EXE%"
    exit /b 1
)

if not exist "%TWS_EXE%" (
    echo ERRO: executavel do TWS nao encontrado: "%TWS_EXE%"
    exit /b 1
)

call :is_tws_running
if errorlevel 1 (
    echo A abrir TWS sem bloquear...
    start "" "%TWS_EXE%"
) else (
    echo TWS ja esta em execucao. A reutilizar a instancia actual.
)

echo A aguardar TWS ficar presente...
call :wait_for_tws_process %TWS_WAIT_TIMEOUT%
if errorlevel 1 (
    echo.
    echo ERRO: TWS nao apareceu no timeout de %TWS_WAIT_TIMEOUT%s. Launcher abortado.
    exit /b 1
)

echo TWS detectado. A executar auto-login...
"%PYTHON_EXE%" "%~dp0tws_autologin.py" --skip-launch --timeout %TWS_WAIT_TIMEOUT%
if errorlevel 1 (
    echo.
    echo AVISO: auto-login falhou - a continuar sem login automatico.
    echo Faz login manualmente no TWS nos proximos 30 segundos.
    timeout /t 30 /nobreak >nul
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

goto :eof

:is_tws_running
tasklist /FI "IMAGENAME eq %TWS_PROCESS%" 2>nul | find /I "%TWS_PROCESS%" >nul
if errorlevel 1 exit /b 1
exit /b 0

:wait_for_tws_process
set "WAIT_SECONDS=%~1"
set /a ELAPSED=0
:wait_for_tws_process_loop
call :is_tws_running
if not errorlevel 1 exit /b 0
if !ELAPSED! geq %WAIT_SECONDS% exit /b 1
timeout /t 1 /nobreak >nul
set /a ELAPSED+=1
goto :wait_for_tws_process_loop
