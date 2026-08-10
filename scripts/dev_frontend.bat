@echo off
REM Synora Bridge (Nuxt 4) - development launcher
REM Starts the Nuxt dev server on http://localhost:3000
cd /d "%~dp0..\frontend"
if not exist "node_modules" (
    echo Installing dependencies...
    call npm install
)
echo Starting Nuxt dev server...
call npm run dev
