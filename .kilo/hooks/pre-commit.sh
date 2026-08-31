#!/usr/bin/env bash
set -euo pipefail

echo "[pre-commit] Running lint..."
ruff check src/ scripts/ tests/

echo "[pre-commit] Running typecheck..."
mypy src/ scripts/

echo "[pre-commit] Running tests..."
pytest tests/ -q

echo "[pre-commit] Validating JSON..."
python scripts/validate.py

echo "[pre-commit] OK"
