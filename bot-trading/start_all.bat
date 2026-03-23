@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Launcher - TWS + Bot + Dashboard
cd /d "%~dp0"

set "TWS_EXE=C:\Jts\tws.exe"
set "TWS_PROCESS=tws.exe"
set "TWS_WAIT_TIMEOUT=60"
set "AUTOLOGIN_BUFFER_SECONDS=60"
set "PYTHON_EXE="

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

call :resolve_python
if errorlevel 1 (
    echo ERRO: Python do projeto nao encontrado em venv\Scripts\python.exe nem venv2\Scripts\python.exe
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

echo A aguardar 5 segundos para a janela do TWS estabilizar...
timeout /t 5 /nobreak >nul

echo TWS detectado. A executar auto-login...
call "%PYTHON_EXE%" "%~dp0tws_autologin.py"
if errorlevel 1 (
    echo.
    echo ERRO: tws_autologin.py falhou. Launcher abortado.
    exit /b 1
)

echo Auto-login concluido. A aguardar %AUTOLOGIN_BUFFER_SECONDS% segundos completos antes de arrancar dashboard e bot...
timeout /t %AUTOLOGIN_BUFFER_SECONDS% /nobreak >nul

echo.
echo Buffer de login concluido. A arrancar dashboard e bot...
echo.

rem Abrir dashboard numa janela separada
start "Dashboard de Trading" cmd /k "cd /d "%~dp0" && "%PYTHON_EXE%" -m streamlit run dashboard/app.py --server.port 8501 --server.headless true --server.address 0.0.0.0"

rem Aguardar dashboard arrancar
timeout /t 3 /nobreak >nul

rem Abrir browser
start http://localhost:8501

rem Arrancar bot nesta janela
echo A arrancar bot...
echo.
"%PYTHON_EXE%" main.py

goto :eof

:is_tws_running
tasklist /FI "IMAGENAME eq %TWS_PROCESS%" 2>nul | find /I "%TWS_PROCESS%" >nul
if errorlevel 1 exit /b 1
exit /b 0

:resolve_python
if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
    exit /b 0
)
if exist "%~dp0venv2\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0venv2\Scripts\python.exe"
    exit /b 0
)
exit /b 1

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
