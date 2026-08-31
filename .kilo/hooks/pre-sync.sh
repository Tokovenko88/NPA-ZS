#!/usr/bin/env bash
set -euo pipefail

echo "[pre-sync] Running dry-run DB diff..."
python scripts/run_site_sync.py --dry-run

echo "[pre-sync] OK"
