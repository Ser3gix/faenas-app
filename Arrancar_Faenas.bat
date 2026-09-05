@echo off
title Gestion de Faenas
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_faenas.ps1"
