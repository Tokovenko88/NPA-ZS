#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-}"
if [ -z "$TARGET" ]; then
  echo "[pre-revision] No target specified"
  exit 1
fi

BACKUP="data/work_tools/backup_$(basename "$TARGET" .json)_$(date +%Y%m%d%H%M%S).json"
echo "[pre-revision] Backing up $TARGET -> $BACKUP"
cp "$TARGET" "$BACKUP"

echo "[pre-revision] OK"
