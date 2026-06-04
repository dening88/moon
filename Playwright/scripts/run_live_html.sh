#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."

if [ "${QIWI_TOKEN:-}" = "" ]; then
  echo "QIWI_TOKEN is required for live mode." >&2
  exit 1
fi

QIWI_MODE=live python3 run_tests.py --html --report reports/live-report.html
