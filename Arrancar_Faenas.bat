@echo off
title Faenas PC
echo Este PC lee los PDF. Los datos van a la nube.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_faenas.ps1"
