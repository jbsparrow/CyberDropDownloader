#!/bin/sh

# User defined variables

PYTHON=""
VENV_DIR=""
COMMANDLINE_ARGS=""
AUTO_UPDATE=true
AUTO_UPDATE_PIP=true
CDL_VERSION=">=7.0,<8.0"

# Parse arguments
HELP=false
SKIP_UPDATE=false
for arg in "$@"
do
    case "$arg" in
        --no-update)
            SKIP_UPDATE=true
            ;;
        -h|--help)
            HELP=true
            ;;
    esac
done

# Define help message
HELP_TEXT=$(cat << EOF

Usage:
  $0 [OPTIONS]

Options:
  --no-update       Skip updating Cyberdrop-DL.
  -h, --help        Show this help message and exit.

Description:
  This script sets up a virtual environment and runs Cyberdrop-DL.
  By default, it ensures that Cyberdrop-DL is installed and up to date.

EOF
)
# Display help message
if [ "$HELP" = true ]; then
    echo "$HELP_TEXT"
    exit 0
fi

# Check the installed Python version
MIN_PYTHON_VER="3.11"
MAX_PYTHON_VER="3.14"

if [ -z "$PYTHON" ]
then
    PYTHON=python3
fi

"$PYTHON" -c "
import sys

MIN_PYTHON_VER = tuple(map(int, '$MIN_PYTHON_VER'.split('.')))
MAX_PYTHON_VER = tuple(map(int, '$MAX_PYTHON_VER'.split('.')))
current_version = sys.version_info

exit(0 if (current_version >= MIN_PYTHON_VER and current_version < MAX_PYTHON_VER) else 1)
"

if [ $? -ne 0 ]; then
    "$PYTHON" -V
    echo "Unsupported Python version installed. Needs version >= $MIN_PYTHON_VER and < $MAX_PYTHON_VER"
    exit 1
fi


# Create and activate venv

if [ -z "$VENV_DIR" ]
then
    VENV_DIR="${0%/*}/venv"
fi

if [ ! -f "${VENV_DIR}/bin/activate" ]
then
    echo Creating virtual environment
    "$PYTHON" -m venv "${VENV_DIR}"
    echo
fi


echo Attempting to start venv
. "${VENV_DIR}/bin/activate"
echo

if [ "$AUTO_UPDATE_PIP" = true ]; then
    echo Updating PIP
    "$PYTHON" -m pip install --upgrade pip
    echo
fi

pip uninstall -y -qq cyberdrop-dl
# Ensure Cyberdrop-DL is installed
if ! command -v cyberdrop-dl >/dev/null 2>&1; then
    echo Cyberdrop-DL is not installed, installing...
    pip install "cyberdrop-dl-patched${CDL_VERSION}"
    echo
    if [ $? -ne 0 ]; then
        echo "Failed to install Cyberdrop-DL."
        exit 1
    fi
    if ! command -v cyberdrop-dl >/dev/null 2>&1; then
        echo Cyberdrop-DL was successfully installed, but could not be found in the virtual environment.
        exit 1
    fi
else
    if [ "$AUTO_UPDATE" = true ] && [ "$SKIP_UPDATE" = false ]; then
        echo Updating Cyberdrop-DL...
        pip install --upgrade "cyberdrop-dl-patched${CDL_VERSION}"
        echo
    fi
fi


clear && cyberdrop-dl $COMMANDLINE_ARGS
