@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Demo.ps1" %*
if errorlevel 1 (
  echo.
  echo CareerProof failed to start. Read the error above and check Docker Desktop.
  pause
  exit /b 1
)

echo.
echo Launcher completed. Read the startup or preflight status above.
exit /b 0
