@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\instalar.ps1" -Consola
echo.
echo (si ves un error arriba, mandalo)
pause
