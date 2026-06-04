#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."
QIWI_MODE=mock python3 -m unittest discover -s tests -p "test_*.py" -v
