#!/usr/bin/env bash
set -euo pipefail

# Hermes Portable — Linux Build Helper
# 在 Linux 机器上运行此脚本，重建 Linux 兼容的 Python 和 venv
# 用法: cd /path/to/HermesPortable && ./linux-rebuild.sh

HERE="$(cd "$(dirname "$0")" && pwd)"
echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║   Hermes Portable — Linux Rebuild    ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# Check Python 3.12
if ! command -v python3.12 &>/dev/null; then
    echo "[ERROR] Python 3.12 not found. Install it first:"
    echo "  Ubuntu/Debian: sudo apt install python3.12 python3.12-venv"
    echo "  Fedora:        sudo dnf install python3.12"
    exit 1
fi

echo "[1/3] 重建 Linux Python 运行时..."
# Remove old macOS Python
rm -rf "$HERE/python"
mkdir -p "$HERE/python"

# Use system Python as portable Python (create structure)
SYS_PY=$(which python3.12)
SYS_PY_DIR=$(dirname "$(dirname "$SYS_PY")")
echo "  源: $SYS_PY_DIR"
cp -a "$SYS_PY_DIR"/* "$HERE/python/" 2>/dev/null || true
echo "  ✅ Python 已就位"

echo "[2/3] 重建 venv..."
rm -rf "$HERE/venv"
python3.12 -m venv "$HERE/venv"

echo "[3/3] 安装依赖..."
"$HERE/venv/bin/pip" install --upgrade pip
"$HERE/venv/bin/pip" install -e "$HERE/hermes-agent[cron,messaging,cli,mcp,web]"

echo ""
echo "  ✅ Linux 重建完成！"
echo ""
echo "  启动: ./Hermes.sh"
echo ""
