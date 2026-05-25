#!/usr/bin/env bash
# Lokální dev build (POSIX). Pro Windows .exe build viz .github/workflows/build-windows.yml.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d ".venv" ]]; then
  echo "Vytvářím .venv s Python 3.11+…"
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -e ".[dev]"

echo
echo "Hotovo. Spusť aplikaci:"
echo "  source .venv/bin/activate"
echo "  python -m app"
echo
echo "Smoke test:"
echo "  python scripts/smoke_test.py path/to/audio.mp3"
