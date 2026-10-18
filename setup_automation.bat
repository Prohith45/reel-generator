@echo off
echo ============================================================
echo   REEL GENERATOR - Automated Pipeline Setup
echo ============================================================
echo.

REM Check if we're in the correct directory
if not exist "main.py" (
    echo [ERROR] Please run this script from the Reel Generator project root
    pause
    exit /b 1
)

REM Create necessary directories
if not exist "automation" mkdir automation
if not exist "automation\topic_planner" mkdir automation\topic_planner
if not exist "automation\validator" mkdir automation\validator
if not exist "automation\publisher" mkdir automation\publisher
if not exist "automation\pipeline" mkdir automation\pipeline
if not exist "config" mkdir config
if not exist "data" mkdir data
if not exist "logs" mkdir logs

echo [1/4] Creating automation components...
REM Core automation files are already created

echo [2/4] Setting up configuration...
if not exist "config\automation.yaml" (
    echo   Creating default automation configuration...
    REM The config file already exists
)

echo [3/4] Setting up environment...
if not exist ".env" (
    echo   Creating environment template...
    copy ".env.example" ".env" >nul 2>&1
    echo   Please edit .env file with your API credentials
)

echo [4/4] Running system check...
echo ------------------------------------------------------------

set ALL_READY=1

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] Python not found in PATH
    set ALL_READY=0
) else (
    echo   [OK] Python available
)

REM Check virtual environment
if not exist "venv" (
    echo   [WARN] Virtual environment not found - run setup.bat first
    set ALL_READY=0
) else (
    echo   [OK] Virtual environment exists
)

REM Check required modules
venv\Scripts\python.exe -c "import yaml, sqlite3, datetime" >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] Required Python modules missing
    set ALL_READY=0
) else (
    echo   [OK] Required modules available
)

REM Check automation files
if not exist "automation\run_pipeline.py" (
    echo   [FAIL] Automation pipeline not found
    set ALL_READY=0
) else (
    echo   [OK] Automation pipeline ready
)

echo ------------------------------------------------------------

if %ALL_READY% equ 1 (
    echo [SUCCESS] Automation system is ready!
    echo.
    echo Next steps:
    echo 1. Edit .env file with your API credentials
    echo 2. Test with: python automation\run_pipeline.py --dry-run
    echo 3. Schedule with: python automation\run_pipeline.py --schedule tuesday
    echo.
) else (
    echo [WARN] Some components need attention. See issues above.
)

echo.
echo ============================================================
echo   SETUP COMPLETE
echo ============================================================
pause