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
# on e.g. Apple Silicon) gets copied to a different-arch host (e.g.
# Intel Mac). `uname -m` detects the host correctly, but because
# the zip only ships `venv/` (not `venv-macos-arm64/`), the launcher
# happily uses the wrong venv. `exec`-ing those binaries then fails
# with a cryptic "Bad CPU type in executable" / "Killed: 9", deep
# inside the script, after the lock + symlink + webui have already
# been set up. Detect the mismatch up front via `file -b` and bail
# with an explanation the user can actually act on.
#
# Universal zips are NOT affected: they already carry per-arch
# `venv-macos-arm64/` and `venv-macos-x64/` and the detection above
# picks the right one. Only the platform-only `venv/` fallback can
# be wrong.
MISMATCH=""
ARCH_PROBE="$VENV_DIR/bin/hermes"
[ -x "$ARCH_PROBE" ] || ARCH_PROBE="$VENV_DIR/bin/python"
if [ -x "$ARCH_PROBE" ] && command -v file >/dev/null 2>&1; then
  BIN_INFO="$(file -b "$ARCH_PROBE" 2>/dev/null || true)"
  case "$ARCH" in
    x86_64|amd64)
      # Need x86_64 or a universal (fat) binary; pure arm64 is wrong.
      if ! echo "$BIN_INFO" | grep -qE "x86_64|universal"; then
        if echo "$BIN_INFO" | grep -q "arm64"; then
          MISMATCH="arm64 (Apple Silicon)"
        fi
      fi
      ;;
    arm64|aarch64)
      # arm64 Mac *can* run x86_64 via Rosetta 2, but only when it's
      # installed — and a plain `venv/` carrying x86_64 still signals
      # the zip was mis-selected (e.g. Intel build on an M-series Mac).
      # Refuse and let the user grab the right zip.
      if ! echo "$BIN_INFO" | grep -qE "arm64|universal"; then
        if echo "$BIN_INFO" | grep -q "x86_64"; then
          MISMATCH="x86_64 (Intel)"
        fi
      fi
      ;;
  esac
fi
if [ -n "$MISMATCH" ]; then
  echo "" >&2
  echo "  [ERROR] CPU architecture mismatch." >&2
  echo "" >&2
  echo "  This Mac : $OS $ARCH" >&2
  echo "  venv arch: $MISMATCH" >&2
  echo "    probe   : $ARCH_PROBE" >&2
  echo "    file    : $BIN_INFO" >&2
  echo "" >&2
  echo "  The venv inside this folder was built for a different CPU and" >&2
  echo "  cannot run here. This usually means the HermesPortable folder" >&2
  echo "  was copied from a Mac with a different chip (Apple Silicon <-> Intel)." >&2
  echo "  macOS does not cross-run arm64 and x86_64 code without Rosetta 2," >&2
  echo "  and even then some native extensions break — the clean fix is to" >&2
  echo "  rebuild the runtime on THIS Mac. Your data/ and API keys survive." >&2
  echo "" >&2
  # Prefer the in-place rebuild if the helper is available (platform-only
  # zips ship mac-rebuild.sh + build.py). Universal zips strip build.py
  # to save space, so they fall back to the download path.
  if [ -f "$HERE/mac-rebuild.sh" ] && [ -f "$HERE/build.py" ]; then
    echo "  Recommended fix (rebuilds the runtime on this Mac, ~2-3 min):" >&2
    echo "    bash \"$HERE/mac-rebuild.sh\"" >&2
    echo "" >&2
    echo "  Requires Xcode Command Line Tools (python3 + git + curl)." >&2
    echo "  If you don't have them:  xcode-select --install" >&2
    echo "" >&2
    echo "  After it finishes, double-click Hermes.command again." >&2
  else
    echo "  Fix, pick one:" >&2
    echo "    1. Download HermesPortable-Universal.zip (ships both Mac arches):" >&2
    echo "         https://github.com/yuluyangguang1/hermes-portable/releases" >&2
    echo "    2. Or download the macOS zip built for $ARCH." >&2
    echo "    3. Or grab the source repo and run:  python3 build.py" >&2
  fi
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
# one machine and shebangs ended up absolute (or if mac-rebuild.sh
# just regenerated the venv at a new absolute path), they break
# when the folder moves. fix_shims.py rewrites them to the local
# python. Harmless (no-op) when shebangs are already `/bin/sh`-
# wrapped relocatable stubs, which is the common case on macOS.
# Kept in sync with Hermes.sh — previously only Hermes.sh ran this.
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
CONFIG_PID=""
OWN_LOCK=0
cleanup() {
  # Kill config server if still alive
  if [ -n "$CONFIG_PID" ] && kill -0 "$CONFIG_PID" 2>/dev/null; then
    kill "$CONFIG_PID" 2>/dev/null || true
  fi
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

# ── Single-instance lock (atomic via noclobber) ───────────────
# Atomic create-or-fail: `set -C` makes the subsequent `>` bail with a
# non-zero status if the file already exists. Two concurrent launches
# racing here both try to `set -C` + redirect; exactly one wins, the
# other drops into the "already running" branch. The plain `[ -f ]`
# test we had before was a TOCTOU race — both shells could pass it,
# then both write their PID, and the last writer "owned" the lock
# while the first kept `OWN_LOCK=1` and still ran hermes.
mkdir -p "$HERE/data"
LOCK="$HERE/data/.hermes.lock"
# First try to atomically claim a brand-new lock file.
if ! ( set -C; echo $$ > "$LOCK" ) 2>/dev/null; then
  # File already exists. Read the stored PID; if that process is
  # alive, refuse. Otherwise it's a stale lock (crash or force-kill)
  # and we try to reclaim it.
  OLD_PID="$(cat "$LOCK" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "  Hermes already running (PID $OLD_PID)."
    echo "  If that is wrong, delete: $LOCK"
    exit 1
  fi
  # Stale — delete and try the atomic claim once more. If some OTHER
  # launcher instance slipped in between the unlink and the retry,
  # it wins and we bail.
  rm -f "$LOCK"
  if ! ( set -C; echo $$ > "$LOCK" ) 2>/dev/null; then
    echo "  Another Hermes launcher beat us to the lock. Try again."
    exit 1
  fi
fi
OWN_LOCK=1

# ── Banner ──────────────────────────────────────────────────
GOLD='\033[38;5;220m'
AMBER='\033[38;5;214m'
BRONZE='\033[38;5;166m'
NC='\033[0m'
echo ""
echo -e "${GOLD}  ██╗   ██╗██╗  ██╗   ██╗ ██████╗${NC}"
echo -e "${GOLD}  ╚██╗ ██╔╝██║  ╚██╗ ██╔╝██╔════╝${NC}"
echo -e "${AMBER}   ╚████╔╝ ██║   ╚████╔╝ ██║  ███╗${NC}"
echo -e "${AMBER}    ╚██╔╝  ██║    ╚██╔╝  ██║   ██║${NC}"
echo -e "${BRONZE}     ██║   ███████╗██║   ╚██████╔╝${NC}"
echo -e "${BRONZE}     ╚═╝   ╚══════╝╚═╝    ╚═════╝${NC}"
echo ""
echo "        Hermes Portable"
echo ""

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

# ── Background config server (always available for model changes) ──
CONFIG_PID=""
export HERMES_BROWSER_OPENED=1
"$VENV_DIR/bin/python" "$HERE/config_server.py" >/dev/null 2>&1 &
CONFIG_PID=$!
echo "  Config panel: http://127.0.0.1:17520 (change model anytime)"

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
