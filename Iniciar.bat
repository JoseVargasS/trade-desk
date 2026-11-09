@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\instalar.ps1"
if errorlevel 1 (
    echo.
    echo No se pudo preparar o iniciar Trade Desk. Revisa el error anterior.
    pause
    exit /b 1
)
