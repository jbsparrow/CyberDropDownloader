#!/bin/sh
# User defined variables
COMMANDLINE_ARGS=""
AUTO_UPDATE=true

# ----------------------------------------------------------
PACKAGE_NAME="cyberdrop-dl-patched"
PACKAGE_VERSION=">=8.0,<9.0"

is_installed() {
    command -v "$1" >/dev/null 2>&1
}

if ! is_installed uv; then
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

    if [ $? -ne 0 ]; then
        echo "Error: Failed to install uv."
        exit 1
    fi
    uv tool update-shell
fi

if [ "$AUTO_UPDATE" = true ] || ! is_installed "${PACKAGE_NAME}"; then
    echo Installing / Updating ${PACKAGE_NAME}...
    uv tool install -p ">=3.12,<3.14" --no-build --upgrade "${PACKAGE_NAME}${PACKAGE_VERSION}" || exit 1
fi

echo Starting ${PACKAGE_NAME}...
uvx -p ">=3.12,<3.14" --no-build "${PACKAGE_NAME}" $COMMANDLINE_ARGS
