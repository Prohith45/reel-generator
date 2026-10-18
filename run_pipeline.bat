@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM   REEL GENERATOR - Unified CLI Runner
REM ============================================================================
REM Usage:
REM   run_pipeline.bat "what is capacitor"
REM   run_pipeline.bat "what is capacitor" --upload youtube
REM   run_pipeline.bat "what is capacitor" --upload instagram
REM   run_pipeline.bat "what is capacitor" --upload none
REM   run_pipeline.bat --dry-run
REM ============================================================================

set PYTHON_CMD=venv\Scripts\python.exe
if not exist "%PYTHON_CMD%" (
    set PYTHON_CMD=python
)

REM If first arg is omitted, let orchestrate.py pick topic automatically
if "%~1"=="" (
    "%PYTHON_CMD%" orchestrate.py --llm api
    goto check_exit
)

set FIRST=%~1
if "%FIRST:~0,2%"=="--" (
    REM First arg is a flag (e.g. --dry-run)
    "%PYTHON_CMD%" orchestrate.py --llm api %*
) else (
    REM First arg is topic string
    "%PYTHON_CMD%" orchestrate.py --topic "%~1" --llm api %2 %3 %4 %5 %6 %7 %8 %9
)

:check_exit
set PIPELINE_EXIT=%ERRORLEVEL%
if %PIPELINE_EXIT% NEQ 0 (
    echo.
    echo [FATAL] Pipeline failed with exit code %PIPELINE_EXIT%.
    exit /b %PIPELINE_EXIT%
)

echo.
echo [SUCCESS] Pipeline execution completed successfully.
exit /b 0
