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

# ── Architecture sanity check ─────────────────────────────────
# Failure mode we're catching: a platform-only zip (`venv/`, built
# on e.g. Apple Silicon or a linux-arm64 box) gets copied to a
# different-arch host. `uname -m` detects the host correctly, but
# because the zip only ships `venv/` (not `venv-$PLATFORM/`), the
# launcher happily uses the wrong venv. `exec`-ing those binaries
# then fails with a cryptic "Bad CPU type in executable" / "Killed:
# 9" / "Exec format error", deep inside the script, after the lock
# + symlink + webui have already been set up. Detect the mismatch
# up front via `file -b` and bail with an explanation the user can
# actually act on.
#
# Universal zips are NOT affected: they already carry per-arch
# `venv-macos-arm64/`, `venv-linux-x64/`, etc., and the detection
# above picks the right one. Only the platform-only `venv/`
# fallback can be wrong.
MISMATCH=""
ARCH_PROBE="$VENV_DIR/bin/hermes"
[ -x "$ARCH_PROBE" ] || ARCH_PROBE="$VENV_DIR/bin/python"
if [ -x "$ARCH_PROBE" ] && command -v file >/dev/null 2>&1; then
  BIN_INFO="$(file -b "$ARCH_PROBE" 2>/dev/null || true)"
  case "$OS:$ARCH" in
    Darwin:x86_64|Darwin:amd64)
      if ! echo "$BIN_INFO" | grep -qE "x86_64|universal"; then
        echo "$BIN_INFO" | grep -q "arm64" && MISMATCH="arm64 (Apple Silicon)"
      fi
      ;;
    Darwin:arm64|Darwin:aarch64)
      if ! echo "$BIN_INFO" | grep -qE "arm64|universal"; then
        echo "$BIN_INFO" | grep -q "x86_64" && MISMATCH="x86_64 (Intel)"
      fi
      ;;
    Linux:x86_64|Linux:amd64)
      # ELF 64-bit LSB ... x86-64 vs aarch64
      if ! echo "$BIN_INFO" | grep -qE "x86-64|x86_64"; then
        echo "$BIN_INFO" | grep -qE "aarch64|ARM aarch64" && MISMATCH="aarch64 (ARM64)"
      fi
      ;;
    Linux:aarch64|Linux:arm64)
      if ! echo "$BIN_INFO" | grep -qE "aarch64|ARM aarch64"; then
        echo "$BIN_INFO" | grep -qE "x86-64|x86_64" && MISMATCH="x86_64 (Intel/AMD)"
      fi
      ;;
  esac
fi
if [ -n "$MISMATCH" ]; then
  echo "" >&2
  echo "  [ERROR] CPU architecture mismatch." >&2
  echo "" >&2
  echo "  This machine : $OS $ARCH" >&2
  echo "  venv arch    : $MISMATCH" >&2
  echo "    probe      : $ARCH_PROBE" >&2
  echo "    file       : $BIN_INFO" >&2
  echo "" >&2
  echo "  The venv inside this folder was built for a different CPU and" >&2
  echo "  cannot run here. This usually means the HermesPortable folder" >&2
  echo "  was copied from a machine with a different chip" >&2
  echo "  (Apple Silicon <-> Intel, or ARM64 <-> x86_64)." >&2
  echo "" >&2
  echo "  Fix, pick one:" >&2
  echo "    1. Download HermesPortable-Universal.zip (ships all arches):" >&2
  echo "         https://github.com/yuluyangguang1/hermes-portable/releases" >&2
  echo "    2. Or download the $OS zip built on a matching machine." >&2
  echo "    3. Or rebuild on THIS machine:" >&2
  echo "         python3 build.py" >&2
  echo "" >&2
  exit 1
fi

# ── HOME hijack sandbox ───────────────────────────────────────
# $HERE/_home is a private HOME. $HERE/_home/.hermes is a symlink
# pointing to $HERE/data, so any library that reads or writes ~/.hermes
# (hermes-web-ui, some plugins, etc.) lands inside the portable folder.
# The host's real ~/.hermes is never read or touched — zero trace.
mkdir -p "$HERE/data"
SANDBOX="$HERE/_home"
mkdir -p "$SANDBOX"
if [ -L "$SANDBOX/.hermes" ] || [ ! -e "$SANDBOX/.hermes" ]; then
  # Missing or already a symlink: (re)create pointing at data/.
  # -n prevents `ln` from descending into an existing symlinked dir.
  ln -sfn "$HERE/data" "$SANDBOX/.hermes"
elif [ -d "$SANDBOX/.hermes" ]; then
  echo "" >&2
  echo "  [ERROR] $SANDBOX/.hermes exists as a real directory." >&2
  echo "  This is unexpected — the sandbox expects a symlink here." >&2
  echo "  Back up any data inside, then remove it:" >&2
  echo "    rm -rf \"$SANDBOX/.hermes\"" >&2
  echo "" >&2
  exit 1
fi

export HOME="$SANDBOX"
export HERMES_HOME="$HERE/data"
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
if [ -n "$NODE_DIR" ]; then
  export PATH="$VENV_DIR/bin:$NODE_DIR/bin:$PYTHON_DIR:$PATH"
else
  export PATH="$VENV_DIR/bin:$PYTHON_DIR:$PATH"
fi
cd "$HERE"

# ── Self-heal launcher shebangs ───────────────────────────────
# Same class of bug as Windows: if the portable zip was built on
# one machine and shebangs ended up absolute, they break when the
# folder moves. fix_shims.py rewrites them to the local python.
# Harmless (no-op) when shebangs are already `/bin/sh`-wrapped
# relocatable stubs, which is the common case on macOS/Linux.
if [ -f "$HERE/fix_shims.py" ]; then
  PORTABLE_PY=""
  # Prefer the real python-build-standalone binary (never a trampoline).
  for cand in "$PYTHON_DIR"/*/bin/python3.12 \
              "$PYTHON_DIR"/*/bin/python3 \
              "$VENV_DIR/bin/python"; do
    if [ -x "$cand" ]; then PORTABLE_PY="$cand"; break; fi
  done
  if [ -n "$PORTABLE_PY" ]; then
    "$PORTABLE_PY" "$HERE/fix_shims.py" 2>/dev/null || true
  fi
fi

# ── Cleanup: must be reachable even after child exits ─────────
# OWN_LOCK gates the unlink: we only clear the lock file if WE were
# the process that created it. Without this guard, a second launch
# that correctly detects "already running" and exits 1 would still
# run the trap and delete the first instance's lock — making the
# single-instance check useless from the third launch onward.
WEBUI_PID=""
HERMES_PID=""
OWN_LOCK=0
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
  if [ "$OWN_LOCK" = "1" ]; then
    rm -f "$HERE/data/.hermes.lock" 2>/dev/null || true
  fi
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
OWN_LOCK=1

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
  # Tell config_server we already opened the browser, so it doesn't
  # open a second tab (see config_server.main).
  export HERMES_BROWSER_OPENED=1
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
