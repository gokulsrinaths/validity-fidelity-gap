@echo off
setlocal enabledelayedexpansion

cd /d %~dp0

set RUN_ROOT=data\runs\cross_model_llama70b
if not exist %RUN_ROOT% mkdir %RUN_ROOT%

REM If a run is already in progress, avoid clobbering/locking log files.
if exist %RUN_ROOT%\heartbeat.json (
  findstr /c:"\"phase\": \"completed\"" %RUN_ROOT%\heartbeat.json >nul
  if errorlevel 1 (
    echo Detected an in-progress run (heartbeat.json not completed). Exiting without starting a second run.
    exit /b 2
  )
)

echo Running LLaMA 70B cross-model validation...
echo Output root: %RUN_ROOT%

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i

py -3 cross_model_validation.py --model llama70b --run_root %RUN_ROOT% 1>> %RUN_ROOT%\stdout_%TS%.log 2>> %RUN_ROOT%\stderr_%TS%.log
exit /b %ERRORLEVEL%
