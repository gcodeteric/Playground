@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Launcher - TWS + Bot + Dashboard
cd /d "%~dp0"

set "TWS_EXE=C:\Jts\tws.exe"
set "TWS_PROCESS=tws.exe"
set "TWS_WAIT_TIMEOUT=60"
set "AUTOLOGIN_BUFFER_SECONDS=60"
set "API_PORT=7497"
set "API_READINESS_TIMEOUT=120"
set "LAUNCHER_LOG=data\launcher.log"
set "PYTHON_EXE="

echo.
echo ========================================
echo    A ARRANCAR TWS + BOT + DASHBOARD
echo ========================================
echo.

rem --- Garantir que directoria data existe ---
if not exist "data" mkdir "data"

rem --- Iniciar launcher.log ---
echo. >> "%LAUNCHER_LOG%"
echo ============================================================ >> "%LAUNCHER_LOG%"
call :log "LAUNCHER INICIADO"

rem --- Apagar locks de sessoes anteriores ---
if exist "data\bot.instance.lock" (
    del /f "data\bot.instance.lock"
    call :log "Lock anterior removido: data\bot.instance.lock"
    echo Lock anterior removido.
)
for %%f in ("%TEMP%\bot-trading-instance-locks\*.lock") do (
    del /f "%%f" 2>nul
)

rem --- Resolver Python ---
call :resolve_python
if errorlevel 1 (
    call :log "ERRO: Python nao encontrado em venv ou venv2"
    echo ERRO: Python do projeto nao encontrado em venv\Scripts\python.exe nem venv2\Scripts\python.exe
    exit /b 1
)
call :log "Python resolvido: %PYTHON_EXE%"

rem --- Verificar executavel TWS ---
if not exist "%TWS_EXE%" (
    call :log "ERRO: executavel TWS nao encontrado: %TWS_EXE%"
    echo ERRO: executavel do TWS nao encontrado: "%TWS_EXE%"
    exit /b 1
)

rem === ETAPA 1: TWS ===
call :is_tws_running
if errorlevel 1 (
    call :log "ETAPA 1: A abrir TWS (%TWS_EXE%)"
    echo A abrir TWS sem bloquear...
    start "" "%TWS_EXE%"
) else (
    call :log "ETAPA 1: TWS ja em execucao — a reutilizar"
    echo TWS ja esta em execucao. A reutilizar a instancia actual.
)

echo A aguardar TWS ficar presente...
call :wait_for_tws_process %TWS_WAIT_TIMEOUT%
if errorlevel 1 (
    call :log "ERRO: TWS nao apareceu no timeout de %TWS_WAIT_TIMEOUT%s"
    echo.
    echo ERRO: TWS nao apareceu no timeout de %TWS_WAIT_TIMEOUT%s. Launcher abortado.
    exit /b 1
)
call :log "ETAPA 1: TWS detectado como processo activo"

echo A aguardar 5 segundos para a janela do TWS estabilizar...
timeout /t 5 /nobreak >nul

rem === ETAPA 2: AUTO-LOGIN ===
call :log "ETAPA 2: A executar tws_autologin.py"
echo TWS detectado. A executar auto-login...
call "%PYTHON_EXE%" "%~dp0tws_autologin.py"
if errorlevel 1 (
    call :log "ERRO: tws_autologin.py falhou (exit code: %ERRORLEVEL%)"
    echo.
    echo ERRO: tws_autologin.py falhou. Launcher abortado.
    exit /b 1
)
call :log "ETAPA 2: Auto-login concluido com sucesso"

rem === ETAPA 3: BUFFER POS-LOGIN ===
call :log "ETAPA 3: Buffer pos-login iniciado (%AUTOLOGIN_BUFFER_SECONDS%s)"
echo Auto-login concluido. A aguardar %AUTOLOGIN_BUFFER_SECONDS% segundos completos...
timeout /t %AUTOLOGIN_BUFFER_SECONDS% /nobreak >nul
call :log "ETAPA 3: Buffer pos-login concluido"

rem === ETAPA 4: READINESS CHECK TCP ===
call :log "ETAPA 4: Probe TCP em 127.0.0.1:%API_PORT% (timeout=%API_READINESS_TIMEOUT%s)"
echo A verificar se a API do TWS esta pronta na porta %API_PORT%...
"%PYTHON_EXE%" "%~dp0check_tws_ready.py" --port %API_PORT% --timeout %API_READINESS_TIMEOUT%
if errorlevel 1 (
    call :log "ERRO: API TWS nao respondeu na porta %API_PORT% apos %API_READINESS_TIMEOUT%s"
    echo.
    echo ERRO: API do TWS nao esta pronta na porta %API_PORT%. Launcher abortado.
    exit /b 1
)
call :log "ETAPA 4: API TWS pronta na porta %API_PORT%"

echo.
echo API pronta. A arrancar dashboard e bot...
echo.

rem === ETAPA 5: DASHBOARD ===
call :log "ETAPA 5: A lancar dashboard (Streamlit porta 8501)"
start "Dashboard de Trading" cmd /k "cd /d "%~dp0" && "%PYTHON_EXE%" -m streamlit run dashboard/app.py --server.port 8501 --server.headless true --server.address 0.0.0.0"

rem Aguardar dashboard arrancar
timeout /t 3 /nobreak >nul

rem Abrir browser
start http://localhost:8501
call :log "ETAPA 5: Dashboard lancado e browser aberto"

rem === ETAPA 6: BOT ===
call :log "ETAPA 6: A lancar bot (main.py)"
echo A arrancar bot...
echo.
"%PYTHON_EXE%" main.py
set "BOT_EXIT=%ERRORLEVEL%"
call :log "ETAPA 6: Bot terminou com exit code %BOT_EXIT%"

goto :eof

rem ============================================================
rem  FUNCOES AUXILIARES
rem ============================================================

:log
echo [%date% %time%] %~1 >> "%LAUNCHER_LOG%"
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
