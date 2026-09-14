@echo off
REM ==========================================
REM Xianyu Auto Reply - Offline Dependency Packer
REM
REM Download all Python deps to offline_packages/
REM Then copy that folder to the offline machine
REM and run install.bat inside it.
REM
REM Requirements: Internet + Python 3.11+
REM ==========================================

chcp 65001 >nul 2>&1

echo ==========================================
echo   Offline Dependency Packer
echo ==========================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found, please install Python 3.11+
    pause
    exit /b 1
)

REM Run packer script
python "%~dp0scripts\pack_offline_deps.py"

echo.
pause
