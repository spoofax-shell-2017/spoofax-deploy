#!/usr/bin/env bash

set -eu

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Determine Python executable
if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD='python3'
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD='python'
else
  echo "Cannot find 'python3' or 'python' interpreter, please install Python 3"
  exit 1
fi

# Determine PIP executable
if command -v pip3 >/dev/null 2>&1; then
  PIP_CMD='pip3'
elif command -v pip >/dev/null 2>&1; then
  PIP_CMD='pip'
else
  echo "Cannot find 'pip3' or 'pip' to install required libraries, it should be included with a recent Python 3 installation"
  exit 1
fi

# Create and activate virtualenv
VENV="$DIR/.virtualenv"
$PIP_CMD install --quiet --user --upgrade virtualenv
$PYTHON_CMD -m virtualenv --quiet "$VENV" > /dev/null
# Since virtualenv is made by idiots, temporarily disable unbound variable checks when activating virtualenv
set +o nounset
source "$VENV/bin/activate"
set -o nounset

# Install requirements
$PIP_CMD install --quiet --requirement "$DIR/requirements.txt"

# Run script
$PYTHON_CMD -u "$DIR/main.py" $*

# Deactivate virtualenv
deactivate
