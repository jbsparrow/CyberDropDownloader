#!/bin/sh
set -eu

PACKAGE_VERSION=">=10.0,<11.0"
UV_INSTALL_DIR="${UV_INSTALL_DIR:-$HOME/.local/bin}"
export UV_NO_MODIFY_PATH="1"

is_installed() {
    command -v "$1" >/dev/null 2>&1
}

if is_installed uv; then
    UV_BIN="uv"
elif [ -x "$UV_INSTALL_DIR/uv" ]; then
    UV_BIN="$UV_INSTALL_DIR/uv"
else
    echo "uv not found, installing..."
    if is_installed curl; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif is_installed wget; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    elif is_installed pip; then
        pip install uv
    else
        echo "Error: Unable to install uv (curl, wget and pip not found)"
        exit 1
    fi
    UV_BIN="$UV_INSTALL_DIR/uv"
fi

echo Installing / Updating cyberdrop-dl...
"$UV_BIN" tool install -p "<3.15" --no-build --upgrade --force "cyberdrop-dl-patched[apprise]${PACKAGE_VERSION}"
"$UV_BIN" tool update-shell
