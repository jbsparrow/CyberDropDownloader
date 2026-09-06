@echo off
setlocal EnableDelayedExpansion
set "errorlevel="
set "PACKAGE_VERSION=>=10.0,<11.0"
set "UV_NO_MODIFY_PATH=1"

if defined UV_INSTALL_DIR (
    set "uv_dir=%UV_INSTALL_DIR%"
) else (
    set "uv_dir=%USERPROFILE%\.local\bin"
)

set "uv_bin="
where uv >nul 2>&1
if %errorlevel%==0 (
    set "uv_bin=uv"
    goto :found
)

if exist "%uv_dir%\uv.exe" (
    set "uv_bin=%uv_dir%\uv.exe"
    goto :found
)

if exist "%APPDATA%\uv\uv.exe" (
    set "uv_bin=%APPDATA%\uv\uv.exe"
    goto :found
)

echo uv not found, installing...
powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

if exist "%uv_dir%\uv.exe" (
    set "uv_bin=%uv_dir%\uv.exe"
    goto :found
)

if exist "%APPDATA%\uv\uv.exe" (
    set "uv_bin=%APPDATA%\uv\uv.exe"
    goto :found
)

echo ERROR: Unable to find uv after installation.
pause
exit /b 1

:found
echo Installing / Updating cyberdrop-dl...
"%uv_bin%" tool install --managed-python -p "<3.15" --no-build --upgrade --force "cyberdrop-dl-patched[apprise]%PACKAGE_VERSION%"
"%uv_bin%" tool update-shell
endlocal
pause
