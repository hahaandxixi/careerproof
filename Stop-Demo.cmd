@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Stop-Local.ps1" %*
if errorlevel 1 (
  echo.
  echo CareerProof could not stop cleanly. Read the error above before closing this window.
  pause
  exit /b 1
)

echo.
echo Stop launcher completed. Read the status above. PostgreSQL is kept unless -Database was specified.
exit /b 0
