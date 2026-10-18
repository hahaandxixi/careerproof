@echo off
setlocal
cd /d "%~dp0"

rem Thin entry for the normal environment. All parameters are forwarded to Start-Local.ps1,
rem which stays the single implementation: preflight, build reuse, migrations, services and
rem stop all live there. Nothing is installed, reset or started twice by this wrapper.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Local.ps1" %*
if errorlevel 1 (
  echo.
  echo CareerProof did not start. Read the error above: dependency mismatches name the
  echo exact path and version that failed, and nothing was installed or downgraded.
  pause
  exit /b 1
)

echo.
echo Launcher completed. Read the startup or preflight status above.
exit /b 0
