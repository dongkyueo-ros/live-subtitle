@echo off
title Auto Subtitle
cd /d "%~dp0"

if not exist .venv (
    echo [ERROR] .venv not found. Please run setup.bat first.
    pause
    exit /b 1
)

if not exist .env (
    echo [ERROR] .env not found.
    echo Copy .env.example to .env and add your GROQ_API_KEY.
    pause
    exit /b 1
)

if not exist nircmd.exe (
    echo [ERROR] nircmd.exe not found.
    echo Download from https://www.nirsoft.net/utils/nircmd.html
    echo Place nircmd.exe in this folder.
    pause
    exit /b 1
)

echo [1/3] Switching output to CABLE Input...
nircmd.exe setdefaultsounddevice "CABLE In 16 Ch" 1

echo [2/3] Starting Auto Subtitle...
call .venv\Scripts\activate.bat
python auto_subtitle.py

echo [3/3] Restoring output to headphones...
nircmd.exe setdefaultsounddevice "Headphones" 1
echo Done.
pause