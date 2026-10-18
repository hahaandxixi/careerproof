@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Stop-Local.ps1" %*
if errorlevel 1 (
  echo.
  echo CareerProof could not stop safely. Read the error above.
  pause
  exit /b 1
)
echo Website stop completed. Database and saved data are kept unless -Database was specified.
exit /b 0
