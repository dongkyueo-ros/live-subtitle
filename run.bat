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

call .venv\Scripts\activate.bat
python auto_subtitle.py
pause