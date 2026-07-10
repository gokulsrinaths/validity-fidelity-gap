@echo off
setlocal

cd /d %~dp0

REM Replication-focused cross-model run:
REM - Qwen 72B
REM - 10 patients
REM - mid-range repetitions only (2,5,10,16)
REM - 3 runs/condition
REM Total calls = 240

set "RUN_ROOT=data\runs\cross_model_qwen72b_rep3_midrange"
if not exist "%RUN_ROOT%" mkdir "%RUN_ROOT%"

if exist "%RUN_ROOT%\heartbeat.json" (
  findstr /c:"\"phase\": \"completed\"" "%RUN_ROOT%\heartbeat.json" >nul
  if errorlevel 1 (
    echo Detected an in-progress run (heartbeat not completed). Exiting.
    pause
    exit /b 2
  )
)

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%i"

echo Running Qwen 72B replication (midrange, 3 runs/condition)...
echo Output root: %RUN_ROOT%
echo Logs: %RUN_ROOT%\stdout_%TS%.log and %RUN_ROOT%\stderr_%TS%.log
echo.

py -3 cross_model_validation.py --model qwen72b --run_root "%RUN_ROOT%" --patients 10 --repetitions 2,5,10,16 --runs_per_condition 3 1>> "%RUN_ROOT%\stdout_%TS%.log" 2>> "%RUN_ROOT%\stderr_%TS%.log"
set "EC=%ERRORLEVEL%"
echo.
echo Done (exit code %EC%).
pause
exit /b %EC%

