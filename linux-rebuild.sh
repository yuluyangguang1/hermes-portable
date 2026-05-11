#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Hermes Portable — Linux rebuild helper
#
#  When you carried a macOS-built zip onto a Linux host and want to
#  reuse the shared bits (hermes-agent source, data/, launchers)
#  without re-downloading them, run this script to rebuild ONLY the
#  Linux-specific runtime: Python, venv, dependencies.
#
#  This is a thin wrapper over `build.py` that preserves data/.
# ═══════════════════════════════════════════════════════════════
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"

echo
echo "  Hermes Portable — Linux Rebuild"
echo "  --------------------------------"
echo

# ── Figure out which target layout we're in ──
# Platform label matches the one build.py emits and the launcher looks for.
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64)   LABEL="linux-x64" ;;
  aarch64|arm64)  LABEL="linux-arm64" ;;
  *)              LABEL="linux-$ARCH" ;;
esac

# Detect existing layout: universal (venv-linux-x64/) vs platform-only (venv/)
if [ -d "$HERE/venv-$LABEL" ] || [ -d "$HERE/python-$LABEL" ]; then
  LAYOUT="universal"
else
  LAYOUT="platform"
fi

echo "  Host arch : $ARCH  →  label $LABEL"
echo "  Layout    : $LAYOUT"
echo

# ── Pre-flight checks ──
if [ ! -f "$HERE/build.py" ]; then
  echo "  [ERROR] build.py not found next to this script." >&2
  echo "  This helper must live at the root of a HermesPortable/ folder." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "  [ERROR] python3 not found. Install Python 3.12+ first." >&2
  echo "    Ubuntu/Debian: sudo apt install python3.12" >&2
  echo "    Fedora:        sudo dnf install python3.12" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "  [ERROR] curl not found (used by build.py to fetch uv / Node.js)." >&2
  exit 1
fi

# ── Remove only the Linux-side runtime; NEVER touch data/ or hermes-agent/ ──
purge() {
  local target="$1"
  if [ -d "$HERE/$target" ]; then
    echo "  • removing stale $target/"
    rm -rf "$HERE/$target"
  fi
}

if [ "$LAYOUT" = "universal" ]; then
  purge "venv-$LABEL"
  purge "python-$LABEL"
  purge "node-$LABEL"
else
  purge "venv"
  purge "python"
  purge "node"
fi

# ── Delegate to build.py, which is the single source of truth ──
cd "$HERE"

# build.py's --output expects the *parent* of the HermesPortable folder,
# and appends "HermesPortable" itself. If our directory is literally
# called HermesPortable we can just pass its parent; otherwise we rebuild
# in-place by telling build.py to use $HERE directly (it will notice the
# name matches and skip the join).
PARENT="$(dirname "$HERE")"
BASENAME="$(basename "$HERE")"

if [ "$BASENAME" = "HermesPortable" ]; then
  OUT="$PARENT"
else
  # Rare case — user renamed the folder. Point build.py straight at it.
  OUT="$HERE"
fi

if [ "$LAYOUT" = "universal" ]; then
  python3 build.py --layout universal --output "$OUT"
else
  python3 build.py --output "$OUT"
fi

echo
echo "  ✓ Linux rebuild complete"
echo
echo "  Launch with:  ./Hermes.sh"
echo
