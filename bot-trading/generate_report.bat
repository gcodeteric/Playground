@echo off
title Relatório Diário - Bot de Trading
cd /d "%~dp0"

echo.
echo ========================================
echo    A GERAR RELATÓRIO DO DIA...
echo ========================================
echo.

"%~dp0venv\Scripts\python.exe" generate_report.py

echo.
echo ========================================
echo    RELATÓRIO GERADO
echo    Ficheiros em: data\reports\
echo ========================================
echo.

rem Abrir o prompt Claude no bloco de notas
for /f "delims=" %%i in ('dir /b /od "%~dp0data\reports\claude_prompt_*.txt" 2^>nul') do set LATEST=%%i
if defined LATEST (
    echo A abrir prompt para o Claude...
    notepad "%~dp0data\reports\%LATEST%"
)

pause
