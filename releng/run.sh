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

# Create and activate virtualenv
VENV="$DIR/.virtualenv"
$PYTHON_CMD -m pip install --quiet --user --upgrade virtualenv
$PYTHON_CMD -m virtualenv --quiet "$VENV" > /dev/null
# Since virtualenv is made by idiots, temporarily disable unbound variable checks when activating virtualenv
set +o nounset
source "$VENV/bin/activate"
set -o nounset

# Install requirements
$PYTHON_CMD -m pip install --quiet --requirement "$DIR/requirements.txt"

# Run script
$PYTHON_CMD -u "$DIR/main.py" $*

# Deactivate virtualenv
deactivate
