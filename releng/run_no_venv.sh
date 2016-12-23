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

$PYTHON_CMD -m pip install --quiet --user --upgrade --requirement "$DIR/requirements.txt"
$PYTHON_CMD -u "$DIR/main.py" $*
