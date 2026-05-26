@echo off
chcp 65001 >nul
title Auto Subtitle — 환경 설정

echo.
echo  [1/3] Python 확인 중 ...
python --version >nul 2>&1
if errorlevel 1 (
    echo  오류: Python이 설치되어 있지 않습니다.
    echo  https://www.python.org/downloads/ 에서 설치 후 재실행하세요.
    pause & exit /b 1
)
python --version

echo.
echo  [2/3] 가상환경 생성 중 (.venv) ...
if exist .venv (
    echo  이미 존재합니다. 건너뜁니다.
) else (
    python -m venv .venv
)

echo.
echo  [3/3] 패키지 설치 중 ...
call .venv\Scripts\activate.bat
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo  완료.

echo.
echo  ─────────────────────────────────────────────
echo  다음 단계:
echo    1. .env.example 을 복사해 .env 로 저장
echo    2. .env 파일에 GROQ_API_KEY 입력
echo    3. run.bat 실행
echo  ─────────────────────────────────────────────
echo.
pause
