@echo off
setlocal

REM Part 1:
REM - If LLaMA-70B is still running, exit.
REM - If LLaMA-70B is completed, postprocess it (no API calls).
REM - Then start Qwen-72B run (resumable-safe).

cd /d %~dp0

set "LLAMA_ROOT=data\runs\cross_model_llama70b"
set "QWEN_ROOT=data\runs\cross_model_qwen72b"

echo === Cross-model Part 1 ===
echo LLaMA-70B root: %LLAMA_ROOT%
echo Qwen-72B root:  %QWEN_ROOT%
echo.

REM ---- LLaMA status gate ----
if exist "%LLAMA_ROOT%\heartbeat.json" (
  findstr /c:"\"phase\": \"completed\"" "%LLAMA_ROOT%\heartbeat.json" >nul
  if errorlevel 1 goto LLAMA_IN_PROGRESS
  goto LLAMA_COMPLETED
) else (
  echo WARNING: %LLAMA_ROOT%\heartbeat.json not found. Skipping LLaMA-70B postprocess.
  goto START_QWEN
)

:LLAMA_IN_PROGRESS
echo LLaMA-70B appears IN-PROGRESS (heartbeat not completed). Not starting Qwen yet.
echo Wait for %LLAMA_ROOT%\heartbeat.json to show "phase": "completed".
pause
exit /b 2

:LLAMA_COMPLETED
echo LLaMA-70B completed. Postprocessing (no API calls)...
py -3 cross_model_validation.py --postprocess --run_root "%LLAMA_ROOT%"
if errorlevel 1 (
  echo Postprocess failed with exit code %ERRORLEVEL%.
  pause
  exit /b %ERRORLEVEL%
)

:START_QWEN
echo.
echo Starting Qwen-72B run...
if not exist "%QWEN_ROOT%" mkdir "%QWEN_ROOT%"

if exist "%QWEN_ROOT%\heartbeat.json" (
  findstr /c:"\"phase\": \"completed\"" "%QWEN_ROOT%\heartbeat.json" >nul
  if errorlevel 1 (
    echo Detected an in-progress Qwen run (heartbeat not completed). Exiting.
    pause
    exit /b 2
  )
)

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%i"

py -3 cross_model_validation.py --model qwen72b --run_root "%QWEN_ROOT%" 1>> "%QWEN_ROOT%\stdout_%TS%.log" 2>> "%QWEN_ROOT%\stderr_%TS%.log"
set "EC=%ERRORLEVEL%"
echo.
echo Done (exit code %EC%). Logs: %QWEN_ROOT%\stdout_%TS%.log and %QWEN_ROOT%\stderr_%TS%.log
pause
exit /b %EC%

