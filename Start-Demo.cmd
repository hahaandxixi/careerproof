@echo off
setlocal
cd /d "%~dp0"

if not "%~1"=="" (
  echo Usage: Start-Demo.cmd
  pause
  exit /b 2
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Demo.ps1"
if errorlevel 1 (
  echo.
  echo CareerProof failed to start. Read the error above and check Docker Desktop.
  pause
  exit /b 1
)

echo.
echo CareerProof started successfully. This window can now be closed.
pause
