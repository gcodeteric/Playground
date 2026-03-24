@echo off
title Bot de Trading
cd /d "%~dp0"

echo.
echo ========================================
echo    BOT DE TRADING - PAPER TRADING
echo ========================================
echo.
echo AVISO: Este script arranca o bot SEM lancar TWS nem autologin.
echo         Use start_all.bat para o fluxo completo.
echo.

rem --- Resolver Python ---
set "PYTHON_EXE="
if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
) else if exist "%~dp0venv2\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0venv2\Scripts\python.exe"
) else (
    echo ERRO: Python nao encontrado em venv ou venv2
    pause
    exit /b 1
)

rem --- Guard de readiness: verificar se API TWS esta acessivel ---
echo A verificar se a API do TWS esta pronta na porta 7497...
"%PYTHON_EXE%" "%~dp0check_tws_ready.py" --port 7497 --timeout 10
if errorlevel 1 (
    echo.
    echo ERRO: API do TWS nao esta acessivel na porta 7497.
    echo       Certifique-se de que o TWS esta aberto e logado.
    echo       Use start_all.bat para o fluxo completo.
    echo.
    pause
    exit /b 1
)

echo API TWS pronta. A arrancar bot...
echo.
"%PYTHON_EXE%" main.py
pause
