@echo off
setlocal

cd /d %~dp0

set "RUN_ROOT=data\runs\cross_model_qwen72b"
if not exist "%RUN_ROOT%" mkdir "%RUN_ROOT%"

REM If a run is already in progress, avoid starting a second one.
if exist "%RUN_ROOT%\heartbeat.json" (
  findstr /c:"\"phase\": \"completed\"" "%RUN_ROOT%\heartbeat.json" >nul
  if errorlevel 1 (
    echo Detected an in-progress Qwen run (heartbeat not completed). Exiting.
    pause
    exit /b 2
  )
)

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%i"

echo Running Qwen 72B cross-model validation...
echo Output root: %RUN_ROOT%
echo Logs: %RUN_ROOT%\stdout_%TS%.log and %RUN_ROOT%\stderr_%TS%.log
echo.

py -3 cross_model_validation.py --model qwen72b --run_root "%RUN_ROOT%" 1>> "%RUN_ROOT%\stdout_%TS%.log" 2>> "%RUN_ROOT%\stderr_%TS%.log"
set "EC=%ERRORLEVEL%"
echo.
echo Done (exit code %EC%).
pause
exit /b %EC%

