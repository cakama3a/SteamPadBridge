@echo off
setlocal
chcp 65001 >nul

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%\build.ps1"
if errorlevel 1 (
    echo.
    echo Build failed. See "%SCRIPT_DIR%\build.log"
    pause
    exit /b 1
)

echo.
echo Build finished.
pause
exit /b 0
