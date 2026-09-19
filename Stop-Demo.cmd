@echo off
setlocal
cd /d "%~dp0"

if not "%~1"=="" (
  echo Usage: Stop-Demo.cmd
  pause
  exit /b 2
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Stop-Local.ps1" -Database
if errorlevel 1 (
  echo.
  echo CareerProof could not stop cleanly. Read the error above before closing this window.
  pause
  exit /b 1
)

echo.
echo CareerProof and its PostgreSQL container have stopped. Saved data remains available.
pause
