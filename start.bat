@echo off
rem Start Appling on Windows (http://127.0.0.1:9200/). Prepares everything on
rem the first run, then runs in the background; stop it with stop.bat.
rem Usage: start.bat [port]
setlocal EnableExtensions

set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
set "PORT=%~1"
if "%PORT%"=="" set "PORT=%LYRA_LITE_PORT%"
if "%PORT%"=="" set "PORT=9200"
set "URL=http://127.0.0.1:%PORT%/"
set "PY=%PROJECT_DIR%\.venv\Scripts\python.exe"
cd /d "%PROJECT_DIR%"

netstat -ano | findstr /R /C:"127.0.0.1:%PORT% .*LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo Something is already running on port %PORT% - probably Appling: %URL%
  echo Stop it with stop.bat, then try again.
  start "" "%URL%"
  exit /b 0
)

where uv >nul 2>&1
if errorlevel 1 (
  echo Error: uv is required. Install it from https://docs.astral.sh/uv/ and run this again.
  exit /b 1
)

if not exist "%PY%" (
  echo Preparing Appling for the first run ^(a few minutes, only once^)...
  uv sync --extra dev
  if errorlevel 1 exit /b 1
)

set "UI=%PROJECT_DIR%\lyra_lite\ui"
if not exist "%UI%\dist\index.html" (
  where npm >nul 2>&1
  if errorlevel 1 (
    echo Error: Node.js ^(npm^) is required to build Appling's screen. Install it from https://nodejs.org/ and run this again.
    exit /b 1
  )
  echo Building Appling's screen...
  pushd "%UI%"
  if not exist node_modules call npm install --no-audit --no-fund
  call npm run build >nul
  popd
)

echo Enabling the Ultimate Builder plugin...
"%PROJECT_DIR%\.venv\Scripts\hermes.exe" plugins enable ultimate-builder >nul 2>&1

if defined HERMES_HOME (set "HOME_DIR=%HERMES_HOME%") else (set "HOME_DIR=%LOCALAPPDATA%\hermes")
set "LOG_DIR=%HOME_DIR%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "LOG=%LOG_DIR%\appling.log"
set "PID_FILE=%LOG_DIR%\appling.pid"

rem Hidden and detached, so closing this window leaves Appling running.
powershell -NoProfile -Command "$p = Start-Process -FilePath $env:PY -ArgumentList '-m','lyra_lite','--port',$env:PORT -WorkingDirectory $env:PROJECT_DIR -WindowStyle Hidden -RedirectStandardOutput $env:LOG -RedirectStandardError ($env:LOG + '.err') -PassThru; Set-Content -Path $env:PID_FILE -Value $p.Id"
if errorlevel 1 (
  echo Appling did not start.
  exit /b 1
)

for /l %%i in (1,1,120) do (
  netstat -ano | findstr /R /C:"127.0.0.1:%PORT% .*LISTENING" >nul 2>&1
  if not errorlevel 1 (
    echo Appling is running at %URL%
    echo Stop it with stop.bat. Log: %LOG%
    exit /b 0
  )
  timeout /t 1 /nobreak >nul
)
echo Appling is still starting. Watch %LOG% and %LOG%.err, or stop it with stop.bat.
