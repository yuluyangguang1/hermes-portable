#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Hermes Portable — thin shell wrapper around update.py
#  Auto-picks the right venv/python for the host platform.
# ═══════════════════════════════════════════════════════════════
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"

# Detect the platform label the launchers and build.py use.
OS="$(uname -s)"
ARCH="$(uname -m)"
case "$OS" in
  Darwin)
    case "$ARCH" in
      arm64)          PLATFORM="macos-arm64" ;;
      x86_64|amd64)   PLATFORM="macos-x64" ;;
      *)              PLATFORM="macos-$ARCH" ;;
    esac ;;
  Linux)
    case "$ARCH" in
      x86_64|amd64)   PLATFORM="linux-x64" ;;
      aarch64|arm64)  PLATFORM="linux-arm64" ;;
      *)              PLATFORM="linux-$ARCH" ;;
    esac ;;
  *)
    echo "  [ERROR] Unsupported OS: $OS" >&2
    exit 1 ;;
esac

# Pick venv Python: try universal layout first, then platform-only.
PY=""
for candidate in \
    "$HERE/venv-$PLATFORM/bin/python" \
    "$HERE/venv/bin/python"; do
  if [ -x "$candidate" ]; then PY="$candidate"; break; fi
done

# Last-resort fallback so `update.py status` can still show *something*
# even if the venv is missing (instead of "command not found").
if [ -z "$PY" ]; then
  if command -v python3 >/dev/null 2>&1; then
    echo "  [warn] No portable venv python found; falling back to system python3." >&2
    PY="$(command -v python3)"
  else
    echo "  [ERROR] No Python found. Expected one of:" >&2
    echo "    $HERE/venv-$PLATFORM/bin/python" >&2
    echo "    $HERE/venv/bin/python" >&2
    exit 1
  fi
fi

export HERMES_HOME="$HERE/data"
exec "$PY" "$HERE/update.py" "${1:-status}"
