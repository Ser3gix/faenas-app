@echo off
title Faenas PC
cd /d "%~dp0"
echo Faenas PC: este ordenador lee los PDF. Los datos van a la nube.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_faenas.ps1"
if errorlevel 1 pause
