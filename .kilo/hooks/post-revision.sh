#!/usr/bin/env bash
set -euo pipefail

echo "[post-revision] Validating result..."
python scripts/validate.py --json data/output/result_npa.json

echo "[post-revision] Generating report..."
python scripts/report.py || true

echo "[post-revision] OK"
