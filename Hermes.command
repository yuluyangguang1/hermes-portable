#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

# ── Platform detection ──
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Darwin)
    case "$ARCH" in
      arm64)  PLATFORM="macos-arm64" ;;
      *)      PLATFORM="macos-x64" ;;
    esac
    ;;
  Linux)
    PLATFORM="linux-x64"
    ;;
  *)
    echo "  不支持的操作系统: $OS"
    exit 1
    ;;
esac

# ── Multi-platform package detection ──
# If per-platform venv exists (universal package), use it
if [ -d "$HERE/venv-$PLATFORM" ]; then
    VENV_DIR="$HERE/venv-$PLATFORM"
    PYTHON_DIR="$HERE/python-$PLATFORM"
# Otherwise fall back to single-platform venv
elif [ -d "$HERE/venv" ]; then
    VENV_DIR="$HERE/venv"
    PYTHON_DIR="$HERE/python"
else
    echo ""
    echo "  [ERROR] 未找到 venv 目录"
    echo "  请先运行构建脚本: python3 build.py"
    echo ""
    exit 1
fi

export HERMES_HOME="$HERE/data"
export PATH="$VENV_DIR/bin:$HERE/node/bin:$PYTHON_DIR:$PATH"
cd "$HERE"

WEBUI_PID=""
cleanup() {
    if [ -n "$WEBUI_PID" ] && kill -0 "$WEBUI_PID" 2>/dev/null; then
        kill "$WEBUI_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# Check if API key is configured
HAS_KEY=false
if [ -f "$HERE/data/.env" ]; then
    if grep -qE '^[A-Z_]+_API_KEY=.{10,}' "$HERE/data/.env" 2>/dev/null; then
        HAS_KEY=true
    fi
fi

if [ "$HAS_KEY" = false ]; then
    echo ""
    echo "  ╦ ╦╔═╗╦═╗╔═╗╔═╗╔═╗╔╦╗╔═╗"
    echo "  ╠═╣╠═╣╠╦╝╠═╝║╣ ║   ║ ║ ║"
    echo "  ╩ ╩╩ ╩╩╚═╩  ╚═╝╚═╝╩ ╩╚═╝  Portable"
    echo ""
    echo "  首次使用！正在打开配置面板..."
    echo "  请在浏览器中完成 API Key 配置。"
    echo "  配置完成后，点击「启动」按钮即可。"
    echo ""
    if command -v open &>/dev/null; then
        open "http://127.0.0.1:17520"
    elif command -v xdg-open &>/dev/null; then
        xdg-open "http://127.0.0.1:17520"
    fi
    exec "$VENV_DIR/bin/python" "$HERE/config_server.py"
fi

# Start hermes-web-ui in background (if installed)
WEBUI_PID=""
if command -v hermes-web-ui &>/dev/null; then
    export PATH="$HERE/node/bin:$PATH"
    hermes-web-ui start --port 8648 &>/dev/null &
    WEBUI_PID=$!
    sleep 2
    if command -v open &>/dev/null; then
        open "http://127.0.0.1:8648"
    elif command -v xdg-open &>/dev/null; then
        xdg-open "http://127.0.0.1:8648"
    fi
fi

exec "$VENV_DIR/bin/hermes" "$@"
