@echo off
REM User defined variables
set "COMMANDLINE_ARGS="
set "AUTO_UPDATE=true"

REM ----------------------------------------------------------
set "PACKAGE_NAME=cyberdrop-dl-patched"
set "PACKAGE_VERSION=>=8.0,<9.0"

if /i "%PROCESSOR_ARCHITECTURE%"=="x86" (
    echo ERROR: 32-bit Windows is not supported.
    pause
    exit /b 1
)

where uv >nul 2>&1
if errorlevel 1 (
    echo uv not found, installing...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    if errorlevel 1 (
        echo Error: Failed to install uv.
        pause
        exit /b 1
    )
    uv tool update-shell
)

set "PACKAGE_INSTALLED=false"
where %PACKAGE_NAME% >nul 2>&1
if %errorlevel%==0 (
    set "PACKAGE_INSTALLED=true"
)

if "%AUTO_UPDATE%"=="true" (
    goto :INSTALL_OR_UPDATE
)

if "%PACKAGE_INSTALLED%"=="false" (
    goto :INSTALL_OR_UPDATE
)
goto :RUN

:INSTALL_OR_UPDATE
echo Installing / Updating %PACKAGE_NAME%...
pip uninstall cyberdrop-dl -qq >nul 2>&1
uv tool install --managed-python -p ">=3.12,<3.14" --no-build --upgrade "%PACKAGE_NAME%%PACKAGE_VERSION%"
if errorlevel 1 (
    echo Error: Failed to install %PACKAGE_NAME%.
    pause
    exit /b 1
)

:RUN
echo Starting %PACKAGE_NAME%...
uvx --managed-python -p ">=3.12,<3.14" --no-build %PACKAGE_NAME% %COMMANDLINE_ARGS%
pause
