@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if errorlevel 1 (
  echo MediaDesk setup failed. Installation files and logs are retained for inspection and retry.
  pause
  exit /b 1
)
pause
