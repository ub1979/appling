@echo off
rem Install the Chromium that Appling's browser checks use, inside Appling's own folder.
setlocal
cd /d "%~dp0.."
if exist ".appling_c\runtime\node_modules\node\node.exe" set "PATH=%CD%\.appling_c\runtime\node_modules\node;%PATH%"
if not defined PLAYWRIGHT_BROWSERS_PATH set "PLAYWRIGHT_BROWSERS_PATH=%CD%\.appling_c\browsers"
if not defined npm_config_cache set "npm_config_cache=%CD%\.appling_c\npm-cache"
cd scripts
call npm ci
if errorlevel 1 exit /b 1
call npx playwright install chromium
exit /b
