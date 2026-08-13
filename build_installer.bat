@echo off
rem =====================================================================
rem  Build the Synora Bridge SETUP installer (Inno Setup 6).
rem
rem  1. Ensures the all-in-one PyInstaller build exists (build_allinone.bat)
rem  2. Reads version/names from launcher\build.properties (single source)
rem  3. Compiles dist\SynoraBridge_Setup_<version>.exe
rem =====================================================================
cd /d "%~dp0"
setlocal

rem 1. All-in-one must exist first
if not exist "dist\allinone\SynoraBridge\SynoraBridge_Launcher.exe" (
    echo [1/3] All-in-one build missing - building it first...
    call build_allinone.bat || goto :err
)

rem 2. Read the single source of truth (launcher\build.properties)
set "VER="
set "EXE="
for /f "usebackq tokens=1,* delims==" %%a in ("launcher\build.properties") do (
    if "%%a"=="version" set "VER=%%b"
    if "%%a"=="exe_name" set "EXE=%%b"
)
set "VER=%VER: =%"
set "EXE=%EXE: =%"
if not defined VER set "VER=6.0"
if not defined EXE set "EXE=SynoraBridge_Launcher"

rem 3. Compile
echo [2/3] Compiling installer for v%VER% ...
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" SynoraBridge_Setup.iss /DMyAppVersion=%VER% /DMyExeName=%EXE%.exe || goto :err

echo [3/3] Done: dist\SynoraBridge_Setup_%VER%.exe
endlocal
exit /b 0

:err
echo Build FAILED.
endlocal
exit /b 1
