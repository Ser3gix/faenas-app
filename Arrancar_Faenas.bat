@echo off
title Gestión de Faenas
color 0A
echo.
echo  =======================================
echo   🪵  Gestión de Faenas — Arrancando...
echo  =======================================
echo.

cd /d "%~dp0"

echo  Iniciando servidor...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_faenas.ps1"

echo.
echo  El servidor se ha detenido.
pause
