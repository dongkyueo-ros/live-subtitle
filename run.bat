@echo off
chcp 65001 >nul
title Auto Subtitle
cd /d "%~dp0"

if not exist .venv (
    echo  가상환경이 없습니다. setup.bat 을 먼저 실행하세요.
    pause & exit /b 1
)

if not exist .env (
    echo  .env 파일이 없습니다.
    echo  .env.example 을 복사해 .env 로 저장 후 API 키를 입력하세요.
    pause & exit /b 1
)

call .venv\Scripts\activate.bat
python auto_subtitle.py
