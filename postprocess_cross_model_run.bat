@echo off
setlocal

cd /d %~dp0

if "%~1"=="" (
  echo Usage: postprocess_cross_model_run.bat ^<RUN_ROOT^>
  echo Example: postprocess_cross_model_run.bat data\runs\cross_model_llama70b_rep3_midrange
  pause
  exit /b 1
)

set "RUN_ROOT=%~1"

echo Postprocessing (no API calls): %RUN_ROOT%
py -3 cross_model_validation.py --postprocess --run_root "%RUN_ROOT%"
set "EC=%ERRORLEVEL%"
echo.
echo Done (exit code %EC%).
pause
exit /b %EC%

