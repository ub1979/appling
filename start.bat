@echo off
rem Start Appling on Windows. This runs natively; WSL is not needed.
rem The first start creates .venv, installs Appling and builds the interface.
rem From PowerShell type .\start.bat (plain "start" is a built-in command there).
setlocal
cd /d "%~dp0"
rem Read and write project files as UTF-8 instead of the local code page.
set "PYTHONUTF8=1"
set "PY=.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo Creating the Python environment in .venv ...
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
  if not exist "%PY%" (
    echo Could not create .venv. Install Python 3.11 or newer from python.org and tick "Add python.exe to PATH".
    exit /b 1
  )
)

rem A Node.js unpacked into Appling's own folder is used before any other.
if exist ".appling_c\runtime\node_modules\node\node.exe" set "PATH=%CD%\.appling_c\runtime\node_modules\node;%PATH%"
if not defined PLAYWRIGHT_BROWSERS_PATH set "PLAYWRIGHT_BROWSERS_PATH=%CD%\.appling_c\browsers"
if not defined npm_config_cache set "npm_config_cache=%CD%\.appling_c\npm-cache"

rem Already running: open it instead of rebuilding.
"%PY%" -m appling.service status --quiet
if not errorlevel 1 (
  "%PY%" -m appling.service start %*
  exit /b
)

"%PY%" -c "from appling.server import create_app" >nul 2>nul
if errorlevel 1 (
  echo Installing missing Appling dependencies...
  "%PY%" -m pip install -e ".[test]"
  if errorlevel 1 exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo Node.js was not found. Install Node.js 22 or newer from nodejs.org, then run start.bat again.
  exit /b 1
)
pushd ui
if not exist node_modules (
  call npm ci
  if errorlevel 1 (popd & exit /b 1)
)
call npm run build
if errorlevel 1 (popd & exit /b 1)
popd

"%PY%" -m appling.service start %*
exit /b
