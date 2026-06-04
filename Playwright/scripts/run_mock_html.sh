#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."
QIWI_MODE=mock python3 run_tests.py --html --report reports/mock-report.html
