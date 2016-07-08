#!/usr/bin/env bash

set -eu

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if command -v pip3 >/dev/null 2>&1; then
  pip3 install --user -q -r "$DIR/requirements.txt"
elif command -v pip >/dev/null 2>&1; then
  pip install --user -q -r "$DIR/requirements.txt"
else
  echo "Cannot find 'pip3' or 'pip' to install required libraries, it should be included with a recent Python 3 installation"
fi

if command -v python3 >/dev/null 2>&1; then
  python3 -u "$DIR/main.py" $*
elif command -v python >/dev/null 2>&1; then
  python -u "$DIR/main.py" $*
else
  echo "Cannot find 'python3' or 'python' interpreter, please install Python 3"
fi
