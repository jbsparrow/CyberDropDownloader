@echo off
setlocal enabledelayedexpansion

rem User defined variables

set "PYTHON="
set "VENV_DIR="
set "COMMANDLINE_ARGS="

rem Check the installed Python version
chcp 65001
set MIN_PYTHON_VER=3.11
set MAX_PYTHON_VER=3.13 
if not defined PYTHON (set PYTHON=python)
"%PYTHON%" -c "import sys; MIN_PYTHON_VER = tuple(map(int, '%MIN_PYTHON_VER%'.split('.'))); MAX_PYTHON_VER = tuple(map(int, '%MAX_PYTHON_VER%'.split('.'))); current_version = sys.version_info; exit(0 if (current_version >= MIN_PYTHON_VER and current_version < MAX_PYTHON_VER) else 1)"

if %ERRORLEVEL% equ 1 (
	"%PYTHON%" -V
    echo Unsupported python version installed. Needs version ^>=%MIN_PYTHON_VER% and ^<%MAX_PYTHON_VER%
	pause
    exit /b 1
)


rem Create and activate venv
if not defined VENV_DIR (set "VENV_DIR=%~dp0%venv")

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

rem Program startup
echo Updating PIP
python -m pip install --upgrade pip
echo:

echo Installing / Updating Cyberdrop-DL
pip uninstall -y -q -q cyberdrop-dl
pip install --upgrade "cyberdrop-dl-patched>=5.7,<6.0" && cls && cyberdrop-dl %COMMANDLINE_ARGS%
pause