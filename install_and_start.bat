@echo off
cd /d "%~dp0"
echo ===== Exam Guard: one-time setup =====
if exist venv\Scripts\python.exe goto install
set PYCMD=
py -3.12 --version >nul 2>&1
if not errorlevel 1 set PYCMD=py -3.12
if not defined PYCMD (
    py -3.11 --version >nul 2>&1
    if not errorlevel 1 set PYCMD=py -3.11
)
if not defined PYCMD (
    py -3.10 --version >nul 2>&1
    if not errorlevel 1 set PYCMD=py -3.10
)
if not defined PYCMD set PYCMD=python
echo Using: %PYCMD%
%PYCMD% -m venv venv
if errorlevel 1 (
    echo Could not create the virtual environment.
    echo Install Python 3.10, 3.11 or 3.12 from python.org and tick "Add Python to PATH".
    pause
    exit /b 1
)
:install
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r libs_needed.txt
if errorlevel 1 (
    echo Install failed. Check your internet connection and Python version (3.10 to 3.12).
    pause
    exit /b 1
)
echo.
echo Setup finished. Starting the app...
python exam_monitor_app.py
pause
