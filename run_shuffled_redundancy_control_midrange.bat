@echo off
setlocal enabledelayedexpansion

REM Runs the shuffled redundancy control using the existing environment.
REM This makes API calls (expensive). It is resumable-safe per call folder.

cd /d "%~dp0"

echo === Shuffled Redundancy Control (midrange) ===
echo This will use config.py settings (model/patients/reps/runs).
echo.

py -3 shuffled_redundancy_control.py --run --reps 5,10,16 --runs_per_condition 1 --num_patients 10
if errorlevel 1 (
  echo FAILED with exit code %errorlevel%
  exit /b %errorlevel%
)

echo DONE.
exit /b 0
