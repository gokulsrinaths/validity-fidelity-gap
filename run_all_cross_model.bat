@echo off
setlocal enabledelayedexpansion

cd /d %~dp0

call run_llama70b_validation.bat
if not "%ERRORLEVEL%"=="0" exit /b %ERRORLEVEL%

call run_qwen72b_validation.bat
if not "%ERRORLEVEL%"=="0" exit /b %ERRORLEVEL%

echo All cross-model runs complete. You can now postprocess:
echo   py -3 cross_model_validation.py --postprocess --run_root data\runs\cross_model_llama70b
echo   py -3 cross_model_validation.py --postprocess --run_root data\runs\cross_model_qwen72b

exit /b 0

