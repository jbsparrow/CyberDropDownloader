#!/bin/sh

# User defined variables

PYTHON=""
VENV_DIR=""
COMMANDLINE_ARGS=""

# Check the installed Python version
MIN_PYTHON_VER="3.11"
MAX_PYTHON_VER="3.13"

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

echo Updating PIP
"$PYTHON" -m pip install --upgrade pip
echo

echo Installing / Updating Cyberdrop-DL
pip uninstall -y -q -q cyberdrop-dl
pip install --upgrade "cyberdrop-dl-patched>=5.7,<6.0" && clear && cyberdrop-dl $COMMANDLINE_ARGS
echo