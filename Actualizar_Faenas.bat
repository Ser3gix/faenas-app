@echo off
title Actualizar Faenas
cd /d "%~dp0"
echo Actualizando Faenas. No hace falta git pull.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_faenas.ps1" -SoloActualizar
echo.
pause
