@echo off
REM Synora Bridge (Django) - development launcher
REM Starts daphne on 127.0.0.1:8000
cd /d "%~dp0..\backend"
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] backend\.venv not found. Run: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
    exit /b 1
)
echo Migrating...
".venv\Scripts\python.exe" manage.py migrate
echo Starting daphne on 127.0.0.1:8000...
".venv\Scripts\python.exe" -m daphne -b 127.0.0.1 -p 8000 config.asgi:application
