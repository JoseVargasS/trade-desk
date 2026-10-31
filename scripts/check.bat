@echo off
REM Verificacion local antes de entregar: lint, formato y tests.
REM Uso: scripts\check.bat
cd /d "%~dp0.."

python -m ruff check . || goto :fallo
python -m ruff format --check . || goto :fallo
python -m pytest || goto :fallo

echo.
echo OK: lint, formato y tests
exit /b 0

:fallo
echo.
echo FALLO: revisa lo de arriba
exit /b 1
