@echo off
setlocal
cd /d "%~dp0"

set "DEMO_MODE=Rules"
if /I "%~1"=="ai" set "DEMO_MODE=AI"
if /I "%~1"=="rules" set "DEMO_MODE=Rules"
if not "%~1"=="" if /I not "%~1"=="ai" if /I not "%~1"=="rules" (
  echo Usage: Start-Demo.cmd [rules^|ai]
  pause
  exit /b 2
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Demo.ps1" -Mode "%DEMO_MODE%"
if errorlevel 1 (
  echo.
  echo CareerProof failed to start. Read the error above and check Docker Desktop.
  pause
  exit /b 1
)

echo.
echo CareerProof started successfully. This window can now be closed.
pause
