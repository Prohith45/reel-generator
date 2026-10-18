@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM   REEL GENERATOR - Full Automated Pipeline (Generate & Upload)
REM ============================================================================
REM Usage:
REM   automate.bat "what is capacitor"
REM   automate.bat "what is capacitor" --upload youtube
REM   automate.bat "what is capacitor" --dry-run
REM ============================================================================

if "%~1"=="" (
    echo [ERROR] Missing topic parameter.
    echo Usage: automate.bat "your topic here"
    exit /b 1
)

set TOPIC=%~1
set UPLOAD_TARGET=both
set DRY_RUN_FLAG=

:parse_flags
if "%~2"=="" goto start_pipeline
if /i "%~2"=="--upload" (
    set UPLOAD_TARGET=%~3
    shift
    shift
    goto parse_flags
)
if /i "%~2"=="--dry-run" (
    set DRY_RUN_FLAG=--dry-run
    shift
    goto parse_flags
)
shift
goto parse_flags

:start_pipeline
echo ============================================================
echo   REEL AUTOMATION PIPELINE
echo   Topic: "%TOPIC%"
echo   Upload: %UPLOAD_TARGET%
echo ============================================================
echo.

set PYTHON_EXE=venv\Scripts\python.exe
if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=python
)

REM ────────────────────────────────────────────────────────────
REM [STEP 1/3] Generating Reel for topic...
REM ────────────────────────────────────────────────────────────
echo [STEP 1/3] Generating Reel for topic: "%TOPIC%"...

REM Store start timestamp to identify newly generated video
for /f "delims=" %%a in ('powershell -NoProfile -Command "(Get-Date).ToString('yyyyMMdd_HHmmss')"') do set RUN_TIME=%%a

REM Create temporary file to capture generator output
set TEMP_OUT=%TEMP%\reel_gen_%RANDOM%.log

"%PYTHON_EXE%" main.py --topic "%TOPIC%" --duration 60 --tts kokoro --llm api --overlay 4 --intro 1 > "%TEMP_OUT%" 2>&1
set GEN_EXIT_CODE=%ERRORLEVEL%

REM Display output to console
type "%TEMP_OUT%"

if %GEN_EXIT_CODE% NEQ 0 (
    echo.
    echo [FATAL] Reel generation failed with exit code %GEN_EXIT_CODE%. Aborting upload.
    if exist "%TEMP_OUT%" del "%TEMP_OUT%"
    exit /b %GEN_EXIT_CODE%
)

REM ────────────────────────────────────────────────────────────
REM [STEP 2/3] Verifying output artifact...
REM ────────────────────────────────────────────────────────────
echo.
echo [STEP 2/3] Verifying output artifact...

REM Extract output video path from log output if present
set GENERATED_VIDEO=
for /f "tokens=2 delims==" %%i in ('findstr /i "OUTPUT_VIDEO_PATH=" "%TEMP_OUT%"') do (
    set GENERATED_VIDEO=%%i
)

if exist "%TEMP_OUT%" del "%TEMP_OUT%"

REM Fallback: Find most recently created MP4 in outputs\videos
if "%GENERATED_VIDEO%"=="" (
    for /f "delims=" %%f in ('dir outputs\videos\*.mp4 /b /o-d 2^>nul') do (
        set GENERATED_VIDEO=outputs\videos\%%f
        goto video_found
    )
)

:video_found
if "%GENERATED_VIDEO%"=="" (
    echo [FATAL] No generated video found in outputs\videos\. Aborting upload.
    exit /b 1
)

if not exist "%GENERATED_VIDEO%" (
    echo [FATAL] Video file does not exist: %GENERATED_VIDEO%. Aborting upload.
    exit /b 1
)

REM Check file size > 0
for %%A in ("%GENERATED_VIDEO%") do set FILE_SIZE=%%~zA
if %FILE_SIZE% LEQ 0 (
    echo [FATAL] Output video file is 0 bytes: %GENERATED_VIDEO%. Aborting upload.
    exit /b 1
)

echo [OK] Verified output video: %GENERATED_VIDEO% (%FILE_SIZE% bytes)

REM ────────────────────────────────────────────────────────────
REM [STEP 3/3] Uploading to YouTube & Instagram...
REM ────────────────────────────────────────────────────────────
echo.
echo [STEP 3/3] Uploading to platforms...

REM --- YouTube Upload ---
if /i "%UPLOAD_TARGET%"=="youtube" goto do_youtube
if /i "%UPLOAD_TARGET%"=="both" goto do_youtube
goto check_instagram

:do_youtube
echo.
echo --- Uploading to YouTube Shorts ---
"%PYTHON_EXE%" youtube_uploader.py --video "%GENERATED_VIDEO%" --topic "%TOPIC%" %DRY_RUN_FLAG%
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] YouTube upload encountered an error (exit code %ERRORLEVEL%).
) else (
    echo [OK] YouTube upload finished.
)

:check_instagram
if /i "%UPLOAD_TARGET%"=="instagram" goto do_instagram
if /i "%UPLOAD_TARGET%"=="both" goto do_instagram
goto pipeline_complete

:do_instagram
echo.
echo --- Uploading to Instagram Reels ---
"%PYTHON_EXE%" instagram_uploader.py --video "%GENERATED_VIDEO%" --topic "%TOPIC%" %DRY_RUN_FLAG%
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Instagram upload failed. (Non-fatal, continuing...)
) else (
    echo [OK] Instagram upload finished.
)

:pipeline_complete
echo.
echo ============================================================
echo [SUCCESS] Automation pipeline completed successfully!
echo ============================================================
exit /b 0
