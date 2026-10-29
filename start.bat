@echo off
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
    echo Run install_and_start.bat first.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
python exam_monitor_app.py
pause
