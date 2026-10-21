@echo off
rem Stop the Appling that start.bat started.
setlocal EnableExtensions

if defined HERMES_HOME (set "HOME_DIR=%HERMES_HOME%") else (set "HOME_DIR=%LOCALAPPDATA%\hermes")
set "PID_FILE=%HOME_DIR%\logs\appling.pid"

if not exist "%PID_FILE%" (
  echo Appling is not running.
  exit /b 0
)
set /p PID=<"%PID_FILE%"
tasklist /FI "PID eq %PID%" | findstr /C:"%PID%" >nul 2>&1
if errorlevel 1 (
  echo Appling is not running.
  del "%PID_FILE%" >nul 2>&1
  exit /b 0
)

echo Stopping Appling...
rem /T also stops what Appling started (previews, the Claude program).
taskkill /PID %PID% /T >nul 2>&1
timeout /t 3 /nobreak >nul
taskkill /PID %PID% /T /F >nul 2>&1
del "%PID_FILE%" >nul 2>&1
echo Stopped.
