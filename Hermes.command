#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export HERMES_HOME="$HERE/data"
export PATH="$HERE/venv/bin:$HERE/python:$PATH"
cd "$HERE"

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
    exec "$HERE/venv/bin/python" "$HERE/config_server.py"
fi

exec "$HERE/venv/bin/hermes" "$@"
