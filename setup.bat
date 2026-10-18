@echo off
echo ============================================================
echo   REEL GENERATOR - Complete One-Click Setup ^& Verification
echo ============================================================
echo.

REM 1. Check Python installation
python --version >nul 2>nul
if not errorlevel 1 (
    set PYTHON_CMD=python
    goto python_found
)

py --version >nul 2>nul
if not errorlevel 1 (
    set PYTHON_CMD=py -3
) else (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.11/3.12: https://www.python.org/downloads/
    pause
    exit /b 1
)

:python_found

REM 2. Create virtual environment if missing
if exist "venv" (
    goto venv_done
)

echo [1/5] Creating virtual environment...
%PYTHON_CMD% -m venv venv
if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment!
    pause
    exit /b 1
)
echo [OK] Virtual environment created.

:venv_done

echo.
echo [2/5] Upgrading package managers ^& installing dependencies...
venv\Scripts\python.exe -m pip install --upgrade pip "setuptools<82" wheel -q

echo [INFO] Installing dependencies (CUDA 12.1 enforced via requirements.txt)...
venv\Scripts\python.exe -m pip install --prefer-binary -r requirements.txt -q
if errorlevel 1 (
    if exist "requirements_no_llama.txt" (
        venv\Scripts\python.exe -m pip install --prefer-binary -r requirements_no_llama.txt -q
    )
)

echo.
echo [3/5] Checking GGUF LLM Script Model...
if exist "src\script\model.gguf" (
    goto model_done
)

echo [INFO] model.gguf not found. Downloading DeepSeek-R1-Distill-Qwen GGUF model...
venv\Scripts\python.exe src\script\get_model.py

:model_done

echo.
echo [4/5] Preloading Voice, Translation, and Browser assets...
venv\Scripts\python.exe -c "from transformers import AutoModelForSeq2SeqLM, AutoTokenizer; AutoTokenizer.from_pretrained('facebook/nllb-200-distilled-600M', src_lang='eng_Latn'); AutoModelForSeq2SeqLM.from_pretrained('facebook/nllb-200-distilled-600M', use_safetensors=True)" >nul 2>nul

echo.
echo [5/5] Running System Integrity Diagnostics...
echo ------------------------------------------------------------
set ALL_WORKING=1

REM Check Core Imports
venv\Scripts\python.exe -c "import torch, transformers, moviepy, selenium, yaml, imagehash" >nul 2>nul
if errorlevel 1 (
    echo   [FAIL] Core Python imports failed!
    set ALL_WORKING=0
) else (
    echo   [OK] Core imports verified successfully.
)

REM Check GGUF Model
if exist "src\script\model.gguf" (
    echo   [OK] GGUF script model present.
) else (
    echo   [FAIL] model.gguf is missing!
    set ALL_WORKING=0
)

REM Check Hugging Face Cached Tokenizers/Models
venv\Scripts\python.exe -c "from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('facebook/nllb-200-distilled-600M', src_lang='eng_Latn')" >nul 2>nul
if errorlevel 1 (
    echo   [FAIL] Hugging Face cached tokenizers/models failed to load!
    set ALL_WORKING=0
) else (
    echo   [OK] Hugging Face cached tokenizers/models ready.
)

REM Check Chrome Selenium
venv\Scripts\python.exe -c "from selenium import webdriver; from selenium.webdriver.chrome.options import Options; o=Options(); o.add_argument('--headless=new'); d=webdriver.Chrome(options=o); d.quit()" >nul 2>nul
if errorlevel 1 (
    echo   [FAIL] Chrome/Selenium browser driver failed!
    set ALL_WORKING=0
) else (
    echo   [OK] Chrome/Selenium driver is ready.
)

echo ------------------------------------------------------------
if %ALL_WORKING% equ 1 (
    echo [OK] All systems check out perfectly!
) else (
    echo [WARN] Some components failed verification. See logs above.
)
echo.

echo ============================================================
echo   STARTING REEL GENERATOR APPLICATION
echo ============================================================
echo.
venv\Scripts\python.exe main.py
pause
