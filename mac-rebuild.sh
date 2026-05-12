#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Hermes Portable — macOS rebuild helper
#
#  Use this when the HermesPortable folder was built on a Mac with a
#  different CPU architecture than the one you're running on now
#  (Apple Silicon zip on an Intel Mac, or vice-versa). macOS does
#  not cross-run arm64 and x86_64 binaries without Rosetta 2, so the
#  bundled venv/python/hermes binaries are unusable as-is.
#
#  What this does:
#    - Removes ONLY the arch-specific runtime (venv/, python/, node/,
#      or their universal-layout venv-macos-<arch>/ ... siblings).
#    - Leaves data/ and the hermes-agent/ source tree completely
#      untouched (your API keys, sessions, skills all survive).
#    - Re-runs build.py on THIS Mac so the new runtime is native.
#
#  Mirrors linux-rebuild.sh so both platforms self-heal the same way.
# ═══════════════════════════════════════════════════════════════
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"

echo
echo "  Hermes Portable — macOS Rebuild"
echo "  --------------------------------"
echo

# ── Figure out which target layout we're in ──
# Platform label matches the one build.py emits and the launcher looks for.
ARCH="$(uname -m)"
case "$ARCH" in
  arm64)           LABEL="macos-arm64" ;;
  x86_64|amd64)    LABEL="macos-x64" ;;
  *)               LABEL="macos-$ARCH" ;;
esac

# Detect existing layout: universal (venv-macos-arm64/) vs platform-only (venv/)
if [ -d "$HERE/venv-macos-arm64" ] || [ -d "$HERE/venv-macos-x64" ] \
   || [ -d "$HERE/python-macos-arm64" ] || [ -d "$HERE/python-macos-x64" ]; then
  LAYOUT="universal"
else
  LAYOUT="platform"
fi

echo "  Host arch : $ARCH  ->  label $LABEL"
echo "  Layout    : $LAYOUT"
echo

# ── Pre-flight checks ──
if [ ! -f "$HERE/build.py" ]; then
  echo "  [ERROR] build.py not found next to this script." >&2
  echo "  This helper must live at the root of a HermesPortable/ folder." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "  [ERROR] python3 not found on PATH." >&2
  echo "" >&2
  echo "  Install it first, then re-run this script:" >&2
  echo "    * Xcode CLT:  xcode-select --install    (ships python3 + git)" >&2
  echo "    * Homebrew:   brew install python@3.12" >&2
  echo "" >&2
  echo "  Note: the Python you install is only used to BUILD the portable" >&2
  echo "  runtime. The resulting HermesPortable folder remains self-contained." >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "  [ERROR] curl not found (build.py uses it to fetch uv / Node.js)." >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "  [ERROR] git not found (build.py uses it to clone hermes-agent)." >&2
  echo "  Install Xcode CLT: xcode-select --install" >&2
  exit 1
fi

# ── Remove only the macOS-side runtime; NEVER touch data/ or hermes-agent/ ──
purge() {
  local target="$1"
  if [ -d "$HERE/$target" ]; then
    echo "  - removing stale $target/"
    rm -rf "$HERE/$target"
  fi
}

if [ "$LAYOUT" = "universal" ]; then
  # In universal layout we only wipe the arch that matches THIS host.
  # The other arch's directories (if present) may still be valid for
  # their own target Mac and should survive.
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

# build.py's --output expects the *parent* of the HermesPortable folder
# and appends "HermesPortable" itself (unless the path already ends with
# that name). Mirror linux-rebuild.sh's choice so both helpers behave
# identically regardless of whether the user renamed the folder.
PARENT="$(dirname "$HERE")"
BASENAME="$(basename "$HERE")"

if [ "$BASENAME" = "HermesPortable" ]; then
  OUT="$PARENT"
else
  OUT="$HERE"
fi

if [ "$LAYOUT" = "universal" ]; then
  python3 build.py --layout universal --output "$OUT"
else
  python3 build.py --output "$OUT"
fi

echo
echo "  ok macOS rebuild complete"
echo
echo "  Launch with:  ./Hermes.command  (or double-click Hermes.command)"
echo
