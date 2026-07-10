@echo off
setlocal enabledelayedexpansion

REM Part 2:
REM - Postprocess Qwen-72B (no API calls)

cd /d %~dp0

set QWEN_ROOT=data\runs\cross_model_qwen72b

echo === Cross-model Part 2 ===
echo Qwen-72B root: %QWEN_ROOT%
echo.

if not exist %QWEN_ROOT% (
  echo ERROR: %QWEN_ROOT% does not exist. Run Part 1 first.
  exit /b 1
)

if exist %QWEN_ROOT%\heartbeat.json (
  findstr /c:"\"phase\": \"completed\"" %QWEN_ROOT%\heartbeat.json >nul
  if errorlevel 1 (
    echo Qwen appears IN-PROGRESS (heartbeat not completed). Not postprocessing yet.
    exit /b 2
  )
) else (
  echo WARNING: %QWEN_ROOT%\heartbeat.json not found. Postprocessing anyway.
)

py -3 cross_model_validation.py --postprocess --run_root %QWEN_ROOT%
set EC=%ERRORLEVEL%
echo.
echo Done (exit code %EC%).
pause
exit /b %EC%
