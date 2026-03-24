@echo off
title Instalar Scheduled Task - Bot Trading
cd /d "%~dp0"

echo.
echo ========================================
echo   INSTALAR SCHEDULED TASK
echo   Bot-Trading-AutoStart (diario 03:30)
echo ========================================
echo.
echo NOTA: Este script requer permissoes de Administrador.
echo       Clique direito > Executar como administrador.
echo.

rem --- Verificar se esta a correr como admin ---
net session >nul 2>&1
if errorlevel 1 (
    echo ERRO: Este script precisa de permissoes de Administrador.
    echo       Clique direito > Executar como administrador.
    echo.
    pause
    exit /b 1
)

rem --- Criar a task ---
schtasks /create ^
    /tn "Bot-Trading-AutoStart" ^
    /tr "\"%~dp0start_all.bat\"" ^
    /sc DAILY ^
    /st 03:30 ^
    /rl HIGHEST ^
    /f

if errorlevel 1 (
    echo.
    echo ERRO: Falha ao criar a scheduled task.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   TASK CRIADA COM SUCESSO
echo   Nome: Bot-Trading-AutoStart
echo   Hora: 03:30 diariamente
echo   Script: %~dp0start_all.bat
echo ========================================
echo.
echo Para alterar a hora:
echo   schtasks /change /tn "Bot-Trading-AutoStart" /st HH:MM
echo.
echo Para desactivar:
echo   schtasks /change /tn "Bot-Trading-AutoStart" /disable
echo.
echo Para remover:
echo   schtasks /delete /tn "Bot-Trading-AutoStart" /f
echo.
pause
