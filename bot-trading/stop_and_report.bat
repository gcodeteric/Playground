@echo off
title Encerrar Bot de Trading
cd /d "%~dp0"

echo.
echo ========================================
echo    A ENCERRAR BOT E DASHBOARD
echo ========================================
echo.

rem --- Seleccionar Python disponivel ---
if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=%~dp0venv2\Scripts\python.exe"
)

rem --- Pedir shutdown gracioso via ficheiro de comando ---
echo A criar pedido de shutdown gracioso...
echo shutdown > "%~dp0data\shutdown.request"

rem --- Aguardar que o bot termine de forma limpa (max 30s) ---
set /a WAIT=0
:WAIT_LOOP
timeout /t 2 /nobreak >nul
set /a WAIT+=2
tasklist /fi "WINDOWTITLE eq Bot de Trading*" 2>nul | findstr /I "python" >nul
if errorlevel 1 goto BOT_STOPPED
if %WAIT% GEQ 30 goto FORCE_KILL
goto WAIT_LOOP

:BOT_STOPPED
echo Bot encerrado de forma graciosa (path: gracioso).
echo SHUTDOWN_PATH=gracioso >> "%~dp0data\shutdown_audit.log"
goto REPORT

:FORCE_KILL
echo Timeout atingido - a forcar encerramento (path: forcado).
echo SHUTDOWN_PATH=forcado >> "%~dp0data\shutdown_audit.log"
taskkill /f /fi "WINDOWTITLE eq Bot de Trading*" >nul 2>&1
timeout /t 2 /nobreak >nul

:REPORT
rem Encerrar dashboard
taskkill /f /fi "WINDOWTITLE eq Dashboard de Trading*" >nul 2>&1

rem Gerar relatorio do dia
echo A gerar relatorio do dia...
"%PYTHON_EXE%" generate_report.py

echo.
echo ========================================
echo    BOT ENCERRADO
echo    Relatorio em: data\reports\
echo ========================================
