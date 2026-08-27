@echo off
echo Copia este acceso al escritorio:
echo   %~dp0Faenas PC.url
echo.
copy /Y "%~dp0Faenas PC.url" "%USERPROFILE%\Desktop\Faenas PC.url" >nul
if errorlevel 1 copy /Y "%~dp0Faenas PC.url" "%USERPROFILE%\Escritorio\Faenas PC.url" >nul
echo Listo. Busca "Faenas PC" en el escritorio.
pause
