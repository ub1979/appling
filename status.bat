@echo off
rem Say whether the Appling for this folder is running, and at which address.
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m appling.service status
) else (
  echo Appling is not set up in this folder yet. Run start.bat first.
  exit /b 1
)
exit /b
