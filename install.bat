@echo off
REM Whisk Installer Script for Windows
REM Downloads and installs Whisk grocery list sync tool

setlocal enabledelayedexpansion

set WHISK_DIR=%USERPROFILE%\.whisk
set WHISK_REPO=https://github.com/aarons22/whisk.git
set BIN_DIR=%USERPROFILE%\.local\bin

echo 🥄 Whisk Installer for Windows
echo ===============================
echo.

REM Check for Python 3.10+
echo [INFO] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ from python.org
    pause
    exit /b 1
)

for /f "tokens=2" %%a in ('python --version') do set PYTHON_VERSION=%%a
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set MAJOR=%%a
    set MINOR=%%b
)

if %MAJOR% LSS 3 (
    echo [ERROR] Python 3.10+ required, found %PYTHON_VERSION%
    pause
    exit /b 1
)
if %MAJOR% EQU 3 if %MINOR% LSS 10 (
    echo [ERROR] Python 3.10+ required, found %PYTHON_VERSION%
    pause
    exit /b 1
)

echo [SUCCESS] Python %PYTHON_VERSION% found

REM Check for git
echo [INFO] Checking Git installation...
git --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git is required but not installed
    echo Please install Git from git-scm.com
    pause
    exit /b 1
)

REM Remove existing installation
if exist "%WHISK_DIR%" (
    echo [INFO] Removing existing installation...
    rmdir /s /q "%WHISK_DIR%"
)

REM Clone repository
echo [INFO] Downloading Whisk...
git clone "%WHISK_REPO%" "%WHISK_DIR%"
if errorlevel 1 (
    echo [ERROR] Failed to download Whisk
    pause
    exit /b 1
)

REM Install dependencies
echo [INFO] Installing Python dependencies...
cd /d "%WHISK_DIR%"
python -m pip install --user -e .
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

REM Create bin directory
if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"

REM Create launcher script
echo [INFO] Creating launcher script...
(
echo @echo off
echo cd /d "%WHISK_DIR%"
echo python -m whisk %%*
) > "%BIN_DIR%\whisk.bat"

REM Add to PATH if not already there
echo [INFO] Adding to PATH...
set "CURRENT_PATH=%PATH%"
echo %CURRENT_PATH% | findstr /C:"%BIN_DIR%" >nul
if errorlevel 1 (
    setx PATH "%PATH%;%BIN_DIR%"
    echo [WARNING] Added %BIN_DIR% to PATH
    echo [WARNING] Please restart your command prompt for changes to take effect
)

echo.
echo [SUCCESS] Whisk installed successfully!
echo.
echo Quick Start:
echo   whisk setup     # Run interactive setup
echo   whisk sync      # One-time sync
echo   whisk start     # Start background daemon
echo.
echo If 'whisk' command not found, restart your command prompt.
echo.
pause