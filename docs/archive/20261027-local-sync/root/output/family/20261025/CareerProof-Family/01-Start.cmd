@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0support\Trial.ps1" -Action Start
set "trialExit=%errorlevel%"
echo.
pause
exit /b %trialExit%
