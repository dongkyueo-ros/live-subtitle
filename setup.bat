@echo off
title Auto Subtitle - Setup
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Please install Python 3.9+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] Python OK
echo [2/3] Creating virtual environment...

if exist .venv (
    echo .venv already exists. Skipping.
) else (
    python -m venv .venv
)

echo [3/3] Installing packages...
call .venv\Scripts\activate.bat
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo.
echo Setup complete.
echo.
echo Next steps:
echo   1. Copy .env.example to .env
echo   2. Add your GROQ_API_KEY to .env
echo   3. Run run.bat
echo.
pause