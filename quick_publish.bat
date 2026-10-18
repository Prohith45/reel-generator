@echo off
setlocal enabledelayedexpansion
title AI Reel Generator - One-Click Zero-Prompt Publisher

echo ==============================================================================
echo   AI REEL GENERATOR - ZERO-CLICK PUBLISHER (YouTube Shorts + Instagram)
echo ==============================================================================
echo.

:: 1. Activate Virtual Environment
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at ./venv
    echo Please run setup.bat first!
    pause
    exit /b 1
)

call .\venv\Scripts\activate.bat

:: 2. Topic Resolution
set "CHOSEN_TOPIC=%~1"

if not "%CHOSEN_TOPIC%"=="" goto RUN_PIPELINE

echo Select an option:
echo   [1] Enter a custom topic
echo   [2] Transistor (How a Transistor Works: The Heart of Modern Electronics)
echo   [3] Transformer (How Transformers Step Up and Down Voltage)
echo   [4] Op-Amp (What is an Operational Amplifier)
echo   [5] Ohm's Law (Voltage, Current, and Resistance Explained)
echo   [6] 555 Timer IC (The Legendary Timer Chip)
echo   [7] Upload latest generated reel directly without regenerating
echo.
set /p "CHOICE=Enter choice [1-7] (default: 2): "

if "%CHOICE%"=="1" (
    echo.
    set /p "CHOSEN_TOPIC=Enter your custom topic: "
    if "!CHOSEN_TOPIC!"=="" set "CHOSEN_TOPIC=How a Transistor Works: The Heart of Modern Electronics"
    goto RUN_PIPELINE
)
if "%CHOICE%"=="2" set "CHOSEN_TOPIC=How a Transistor Works: The Heart of Modern Electronics" & goto RUN_PIPELINE
if "%CHOICE%"=="3" set "CHOSEN_TOPIC=How a Transformer Steps Up and Down Voltage" & goto RUN_PIPELINE
if "%CHOICE%"=="4" set "CHOSEN_TOPIC=What is an Operational Amplifier Op-Amp" & goto RUN_PIPELINE
if "%CHOICE%"=="5" set "CHOSEN_TOPIC=Understanding Ohm's Law: Voltage Current and Resistance" & goto RUN_PIPELINE
if "%CHOICE%"=="6" set "CHOSEN_TOPIC=How the 555 Timer IC Generates Pulses" & goto RUN_PIPELINE
if "%CHOICE%"=="7" goto UPLOAD_LATEST

:: Default to Option 2
set "CHOSEN_TOPIC=How a Transistor Works: The Heart of Modern Electronics"

:RUN_PIPELINE
echo.
echo ==============================================================================
echo [LAUNCHING] Pipeline for topic: "!CHOSEN_TOPIC!"
echo Zero-Click Target: YouTube Shorts + Instagram Reels
echo ==============================================================================
echo.

python orchestrate.py --topic "!CHOSEN_TOPIC!" --duration 45 --llm api --tts kokoro --visuals hybrid --upload both --intro no

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Pipeline failed with exit code %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ==============================================================================
echo [SUCCESS] Video generated and published to YouTube and Instagram!
echo ==============================================================================
echo.
pause
exit /b 0

:UPLOAD_LATEST
echo.
echo ==============================================================================
echo [SCANNING] Finding latest generated video in outputs/videos/...
echo ==============================================================================

for /f "delims=" %%F in ('dir /b /a:-d /o:-d outputs\videos\*.mp4 2^>nul') do (
    set "LATEST_VIDEO=outputs\videos\%%F"
    goto FOUND_VIDEO
)

echo [ERROR] No .mp4 files found in outputs/videos/
pause
exit /b 1

:FOUND_VIDEO
echo Found latest video: !LATEST_VIDEO!
echo.
echo Uploading to YouTube Shorts...
python youtube_uploader.py --video "!LATEST_VIDEO!"

echo.
echo Uploading to Instagram Reels (using cached zero-verification session)...
python instagram_uploader.py --video "!LATEST_VIDEO!"

echo.
echo ==============================================================================
echo [COMPLETE] Upload finished!
echo ==============================================================================
pause
exit /b 0
