@echo off
title League Coach OS — Barrios A2I
color 0B

echo.
echo  ╔═══════════════════════════════════════════════╗
echo  ║  LEAGUE COACH OS — Autonomous Daemon          ║
echo  ║  Hit PrintScreen on loading screen = GG       ║
echo  ╚═══════════════════════════════════════════════╝
echo.

:: Navigate to Python brain directory
cd /d "%~dp0packages\agents\python-brain"

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found. Install Python 3.10+
    pause
    exit /b 1
)

:: Check API key
if "%ANTHROPIC_API_KEY%"=="" (
    echo  [WARN] ANTHROPIC_API_KEY not set!
    echo  Set it: set ANTHROPIC_API_KEY=sk-ant-your-key-here
    echo  Or add to .env file
    echo.
)

:: Install deps if needed
if not exist ".venv" (
    echo  Installing dependencies...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt --quiet
) else (
    call .venv\Scripts\activate.bat
)

:: Load .env if exists
if exist ".env" (
    for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
        if not "%%a"=="" if not "%%a:~0,1%"=="#" set "%%a=%%b"
    )
)

:: Launch daemon
echo  Starting League Coach daemon...
echo  (Run as Administrator for global hotkey support)
echo.
python launch.py daemon %*

pause
