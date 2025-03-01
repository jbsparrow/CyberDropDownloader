@echo off
setlocal enabledelayedexpansion

rem User defined variables

set "PYTHON="
set "VENV_DIR="
set "COMMANDLINE_ARGS="
set "AUTO_UPDATE=true"
set "AUTO_UPDATE_PIP=true"

rem Parse arguments
set "HELP=false"
set "SKIP_UPDATE=false"
for %%a in (%*) do (
    if "%%a"=="--no-update" (
        set "SKIP_UPDATE=true"
    ) else if "%%a"=="-h" (
        set "HELP=true"
    ) else if "%%a"=="--help" (
        set "HELP=true"
    )
)

if "%HELP%"=="true" goto :HELP

rem Check the installed Python version
chcp 65001 > nul
set MIN_PYTHON_VER=3.11
set MAX_PYTHON_VER=3.14
if not defined PYTHON (set PYTHON=python)
"%PYTHON%" -c "import sys; MIN_PYTHON_VER = tuple(map(int, '%MIN_PYTHON_VER%'.split('.'))); MAX_PYTHON_VER = tuple(map(int, '%MAX_PYTHON_VER%'.split('.'))); current_version = sys.version_info; exit(0 if (current_version >= MIN_PYTHON_VER and current_version < MAX_PYTHON_VER) else 1)"

if %ERRORLEVEL% equ 1 (
    "%PYTHON%" -V
    echo Unsupported Python version installed. Needs version ^>=%MIN_PYTHON_VER% and ^<%MAX_PYTHON_VER%
    pause
    exit /b 1
)

rem Create and activate venv
if not defined VENV_DIR (set "VENV_DIR=%~dp0venv")

if not exist "%VENV_DIR%" (
    mkdir "%VENV_DIR%"
)

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Creating virtual environment
    "%PYTHON%" -m venv "%VENV_DIR%"
    echo:
)

echo Attempting to start venv
call "%VENV_DIR%\Scripts\activate.bat"
echo:

if "%AUTO_UPDATE_PIP%" == "true" (
  echo Updating pip...
  python -m pip install --upgrade pip
)

pip uninstall -y -qq cyberdrop-dl
rem Ensure Cyberdrop-DL is installed
where cyberdrop-dl >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Cyberdrop-DL is not installed, installing...
    pip install "cyberdrop-dl-patched>=6.0,<7.0"
    if %ERRORLEVEL% neq 0 (
        echo Failed to install Cyberdrop-DL.
        pause
        exit /b 1
    )
    where cyberdrop-dl >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo Cyberdrop-DL was successfully installed, but could not be found in the virtual environment.
        pause
        exit /b 1
    )
) else (
    if "%AUTO_UPDATE%"=="true" if "%SKIP_UPDATE%"=="false" (
        echo Updating Cyberdrop-DL...
        pip install --upgrade "cyberdrop-dl-patched>=6.0,<7.0"
    )
)


cls
cyberdrop-dl %COMMANDLINE_ARGS%
pause

:HELP
echo.
echo Usage:
echo   %~nx0 [OPTIONS]
echo.
echo Options:
echo   --no-update       Skip updating Cyberdrop-DL.
echo   -h, --help        Show this help message and exit.
echo.
echo Description:
echo   This script sets up a virtual environment and runs Cyberdrop-DL.
echo   By default, it ensures that Cyberdrop-DL is installed and up to date.
echo.
exit /b 0
