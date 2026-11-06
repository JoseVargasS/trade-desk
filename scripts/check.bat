@echo off
REM Verificacion local antes de entregar: lint, formato y tests.
REM Uso: scripts\check.bat
cd /d "%~dp0.."

uv run --locked ruff check . || goto :fallo
uv run --locked ruff format --check . || goto :fallo
uv run --locked python -m pytest || goto :fallo

echo.
echo OK: lint, formato y tests
exit /b 0

:fallo
echo.
echo FALLO: revisa lo de arriba
exit /b 1
