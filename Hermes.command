#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Hermes Portable — Unix launcher (macOS .command & Linux .sh)
# ═══════════════════════════════════════════════════════════════
# Note: we intentionally do NOT use `set -e`. The cleanup trap needs
# to run even if hermes exits non-zero, and `wait $CHILD` returning
# non-zero must not abort us before we capture the exit code.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"

# ── Platform detection ────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"
case "$OS" in
  Darwin)
    case "$ARCH" in
      arm64)          PLATFORM="macos-arm64" ;;
      x86_64|amd64)   PLATFORM="macos-x64" ;;
      *)              PLATFORM="macos-$ARCH" ;;
    esac
    ;;
  Linux)
    case "$ARCH" in
      x86_64|amd64)   PLATFORM="linux-x64" ;;
      aarch64|arm64)  PLATFORM="linux-arm64" ;;
      *)              PLATFORM="linux-$ARCH" ;;
    esac
    ;;
  *)
    echo "  Unsupported OS: $OS" >&2
    exit 1
    ;;
esac

# ── Multi-layout venv detection ───────────────────────────────
# Universal zips carry e.g. venv-macos-arm64/; single-platform zips carry venv/.
if [ -d "$HERE/venv-$PLATFORM" ]; then
  VENV_DIR="$HERE/venv-$PLATFORM"
  PYTHON_DIR="$HERE/python-$PLATFORM"
elif [ -d "$HERE/venv" ]; then
  VENV_DIR="$HERE/venv"
  PYTHON_DIR="$HERE/python"
else
  echo "" >&2
  echo "  [ERROR] venv not found for platform: $PLATFORM" >&2
  echo "  Expected one of:" >&2
  echo "    $HERE/venv-$PLATFORM/bin/hermes" >&2
  echo "    $HERE/venv/bin/hermes" >&2
  echo "" >&2
  exit 1
fi

# Node runtime (optional; universal zip has node-<platform>)
if [ -d "$HERE/node-$PLATFORM" ]; then
  NODE_DIR="$HERE/node-$PLATFORM"
elif [ -d "$HERE/node" ]; then
  NODE_DIR="$HERE/node"
else
  NODE_DIR=""
fi

export HERMES_HOME="$HERE/data"
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
if [ -n "$NODE_DIR" ]; then
  export PATH="$VENV_DIR/bin:$NODE_DIR/bin:$PYTHON_DIR:$PATH"
else
  export PATH="$VENV_DIR/bin:$PYTHON_DIR:$PATH"
fi
cd "$HERE"

# ── Cleanup: must be reachable even after child exits ─────────
WEBUI_PID=""
HERMES_PID=""
cleanup() {
  # Kill webui child if still alive
  if [ -n "$WEBUI_PID" ] && kill -0 "$WEBUI_PID" 2>/dev/null; then
    kill "$WEBUI_PID" 2>/dev/null || true
    wait "$WEBUI_PID" 2>/dev/null || true
  fi
  # Kill hermes child if still alive (covers Ctrl-C from this script)
  if [ -n "$HERMES_PID" ] && kill -0 "$HERMES_PID" 2>/dev/null; then
    kill "$HERMES_PID" 2>/dev/null || true
  fi
  rm -f "$HERE/data/.hermes.lock" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ── Single-instance lock (best-effort) ────────────────────────
mkdir -p "$HERE/data"
LOCK="$HERE/data/.hermes.lock"
if [ -f "$LOCK" ]; then
  OLD_PID="$(cat "$LOCK" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "  Hermes already running (PID $OLD_PID)."
    echo "  If that is wrong, delete: $LOCK"
    exit 1
  fi
  rm -f "$LOCK"
fi
echo $$ > "$LOCK"

# ── First-run / --config handling ─────────────────────────────
HAS_KEY=false
if [ -f "$HERE/data/.env" ]; then
  if grep -qE '^[A-Z_]+_API_KEY=.{10,}' "$HERE/data/.env" 2>/dev/null; then
    HAS_KEY=true
  fi
fi

open_url() {
  if command -v open >/dev/null 2>&1; then open "$1"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$1"
  fi
}

if [ "${1-}" = "--config" ] || [ "$HAS_KEY" = "false" ]; then
  echo ""
  echo "  Opening config panel at http://127.0.0.1:17520 ..."
  echo ""
  open_url "http://127.0.0.1:17520"
  # Run in foreground; trap handlers still fire on exit.
  "$VENV_DIR/bin/python" "$HERE/config_server.py"
  exit $?
fi

# ── Background web UI ─────────────────────────────────────────
if command -v hermes-web-ui >/dev/null 2>&1; then
  hermes-web-ui start --port 8648 >/dev/null 2>&1 &
  WEBUI_PID=$!
fi

# ── Run hermes in foreground, BUT NOT with exec ───────────────
# exec would replace this shell and the EXIT trap would never fire,
# leaving the webui child orphaned. Use a normal child + wait.
"$VENV_DIR/bin/hermes" "$@" &
HERMES_PID=$!
wait "$HERMES_PID"
EXITCODE=$?
HERMES_PID=""
exit $EXITCODE
