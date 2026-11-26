@echo off
rem Stop the Appling started from this folder. Running tasks are checkpointed first.
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m appling.service stop
) else (
  echo Appling is not set up in this folder yet. Run start.bat first.
  exit /b 1
)
exit /b
