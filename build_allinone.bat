@echo off
rem =====================================================================
rem  ALL-IN-ONE build: PyInstaller packages the ENTIRE app into the exe —
rem  launcher GUI + backend (source + every dependency) + frontend build
rem  + node runtime. No Inno, no installer — one folder that just works.
rem
rem  Output: dist\allinone\SynoraBridge\SynoraBridge_Launcher.exe
rem =====================================================================
cd /d "%~dp0"
setlocal

echo [1/5] Staging a clean backend copy (no venv/caches)...
if exist installer_stage rmdir /s /q installer_stage
mkdir installer_stage
robocopy backend installer_stage\backend /E /XD .venv __pycache__ .pytest_cache node_modules ^
    /XF *.pyc *.pyo /NFL /NDL /NJH /NJS /NC /NS >nul
rem Fresh default config (development/SQLite) — no real secrets travel in the bundle.
copy /y backend\tests\test_config.ini installer_stage\backend\config.ini >nul

echo [2/5] Staging the node runtime...
mkdir installer_stage\runtime\node
copy /y "C:\Program Files\nodejs\node.exe" installer_stage\runtime\node\node.exe >nul

echo [3/5] Ensuring the frontend production build...
if not exist frontend\.output\server\index.mjs (
    pushd frontend
    call npm install
    call npm run build
    popd
)

echo [4/5] Running PyInstaller (all-in-one onedir)...
backend\.venv\Scripts\pyinstaller.exe launcher_allinone.spec --distpath dist\allinone --noconfirm || goto :err

echo [5/5] Self-check: the bundle must import django and load settings...
del "dist\allinone\SynoraBridge\launcher-service.log" >nul 2>nul
start /wait "" "dist\allinone\SynoraBridge\SynoraBridge_Launcher.exe" --selfcheck
if exist "dist\allinone\SynoraBridge\launcher-service.log" type "dist\allinone\SynoraBridge\launcher-service.log"

echo.
echo Done: dist\allinone\SynoraBridge\SynoraBridge_Launcher.exe — the whole app is inside.
endlocal
exit /b 0

:err
echo Build FAILED.
endlocal
exit /b 1
