@echo off
chcp 65001 >nul
cd /d %~dp0

where py >nul 2>nul
if %errorlevel%==0 (
  set PYTHON_CMD=py
) else (
  set PYTHON_CMD=python
)

if not exist .venv (
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] 無法建立虛擬環境。請先確認 Python 已安裝。
    pause
    exit /b 1
  )
)

call .venv\Scripts\activate
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] 套件安裝失敗，請確認網路連線。
  pause
  exit /b 1
)

echo.
echo GAME PULSE 啟動中...
echo 請開啟 http://127.0.0.1:5000
echo.
python app.py
pause
