#!/usr/bin/env bash
set -euo pipefail

# Hermes Portable — 更新脚本
# 用法: ./update.sh [check|update|status]

HERE="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║   Hermes Portable — Update Tool      ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# Use the portable Python
PY="$HERE/venv/bin/python"
if [ ! -f "$PY" ]; then
    PY="$HERE/python/bin/python3.12"
fi
if [ ! -f "$PY" ]; then
    PY="python3"
fi

export HERMES_HOME="$HERE/data"

"$PY" "$HERE/update.py" "${1:-status}"
