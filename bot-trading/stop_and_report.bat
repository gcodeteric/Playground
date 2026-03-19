@echo off
title Encerrar Bot de Trading
cd /d "%~dp0"

echo.
echo ========================================
echo    A ENCERRAR BOT E DASHBOARD
echo ========================================
echo.

rem Parar o bot graciosamente (Ctrl+C equivalente)
taskkill /f /fi "WINDOWTITLE eq Bot de Trading*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq Dashboard de Trading*" >nul 2>&1

rem Aguardar que os processos terminem
timeout /t 3 /nobreak >nul

rem Gerar relatório do dia
echo A gerar relatório do dia...
"%~dp0venv\Scripts\python.exe" generate_report.py

echo.
echo ========================================
echo    BOT ENCERRADO
echo    Relatório em: data\reports\
echo ========================================
echo.

rem Abrir o prompt Claude no bloco de notas
for /f "delims=" %%i in ('dir /b /od "%~dp0data\reports\claude_prompt_*.txt" 2^>nul') do set LATEST=%%i
if defined LATEST (
    echo A abrir prompt para o Claude...
    notepad "%~dp0data\reports\%LATEST%"
)

pause
