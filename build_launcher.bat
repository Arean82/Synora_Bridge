@echo off
rem Build the Stack Launcher GUI with PyInstaller.
rem   one_dir -> dist\one_dir\SynoraBridge_Launcher\   (fastest start; daily use)
rem   one_file-> dist\one_file\SynoraBridge_Launcher.exe (single portable file)
cd /d "%~dp0"
backend\.venv\Scripts\pyinstaller.exe launcher_onedir.spec --distpath dist\one_dir --noconfirm || goto :err
backend\.venv\Scripts\pyinstaller.exe launcher.spec --distpath dist\one_file --noconfirm || goto :err
echo.
echo Done.
echo   Fast start : dist\one_dir\SynoraBridge_Launcher\SynoraBridge_Launcher.exe
echo   Portable   : dist\one_file\SynoraBridge_Launcher.exe
echo Keep the exe(s) beside backend\ and frontend\ (or set SYNORA_HOME).
exit /b 0
:err
echo Build FAILED.
exit /b 1
