#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Hermes Portable — Unix launcher (macOS .command & Linux .sh)
# ═══════════════════════════════════════════════════════════════
# Note: we intentionally do NOT use `set -e`. The cleanup trap needs
# to run even if hermes exits non-zero, and `wait $CHILD` returning
# non-zero must not abort us before we capture the exit code.
set -u

# ── Parse command line arguments ──────────────────────────────
LAUNCH_MODE="desktop"  # 默认启动桌面版
for arg in "$@"; do
  case "$arg" in
    --cli)
      LAUNCH_MODE="cli"
      shift
      ;;
    --desktop|--gui)
      LAUNCH_MODE="desktop"
      shift
      ;;
  esac
done

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

# ── Preflight self-check ──────────────────────────────────────
preflight_check() {
  local ok=true

  # Check venv
  if [ ! -x "$VENV_DIR/bin/hermes" ]; then
    echo "  [ERROR] venv not found: $VENV_DIR/bin/hermes" >&2
    ok=false
  fi

  # Check Python
  local py_found=false
  for cand in "$PYTHON_DIR"/*/bin/python3 "$PYTHON_DIR"/*/bin/python3.*; do
    if [ -x "$cand" ]; then py_found=true; break; fi
  done
  if [ "$py_found" = "false" ]; then
    echo "  [ERROR] Python not found in $PYTHON_DIR" >&2
    ok=false
  fi

  # Check config_server.py
  if [ ! -f "$HERE/lib/config_server.py" ]; then
    echo "  [ERROR] config_server.py not found" >&2
    ok=false
  fi

  # Check data directory writable
  if ! touch "$HERE/data/.write_test" 2>/dev/null; then
    echo "  [ERROR] data/ directory not writable" >&2
    ok=false
  fi
  rm -f "$HERE/data/.write_test"

  # Check disk space (warn if < 500MB)
  local avail=$(df -k "$HERE" 2>/dev/null | tail -1 | awk '{print $4}')
  if [ -n "$avail" ] && [ "$avail" -lt 512000 ] 2>/dev/null; then
    echo "  [WARNING] Low disk space: $(($avail / 1024))MB" >&2
  fi

  $ok
}

# ── kill_tree ──────────────────────────────────────────────────
kill_tree() {
  local pid="$1"
  [ -z "$pid" ] && return
  [ "$pid" -le 1 ] 2>/dev/null && return
  local children
  children=$(pgrep -P "$pid" 2>/dev/null || true)
  kill "$pid" 2>/dev/null || true
  for child in $children; do
    kill_tree "$child"
  done
}

# ── Cleanup stale ports ──────────────────────────────────────
cleanup_stale_ports() {
  for port in 17520 8648; do
    local pid=$(lsof -ti :$port 2>/dev/null)
    if [ -n "$pid" ]; then
      echo "  Cleaning stale process on port $port (PID $pid)"
      kill_tree $pid
    fi
  done
}

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

# Run preflight check
if ! preflight_check; then
  echo "  Preflight check failed. Exiting."
  exit 1
fi

# Clean stale ports
cleanup_stale_ports

# ── Architecture sanity check ─────────────────────────────────
# Failure mode we're catching: a platform-only zip (`venv/`, built
# on e.g. Apple Silicon) gets copied to a different-arch host (e.g.
# Intel Mac). `uname -m` detects the host correctly, but because
# the zip only ships `venv/` (not `venv-macos-arm64/`), the launcher
# happily uses the wrong venv. `exec`-ing those binaries then fails
# with a cryptic "Bad CPU type in executable" / "Killed: 9", deep
# inside the script, after the lock + symlink have already been set
# up. Detect the mismatch up front via `file -b` and bail
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
  # zips ship tools/mac-rebuild.sh + tools/build.py). Universal zips strip build.py
  # to save space, so they fall back to the download path.
  if [ -f "$HERE/tools/mac-rebuild.sh" ] && [ -f "$HERE/tools/build.py" ]; then
    echo "  Recommended fix (rebuilds the runtime on this Mac, ~2-3 min):" >&2
    echo "    bash \"$HERE/tools/mac-rebuild.sh\"" >&2
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
    echo "    3. Or grab the source repo and run:  python3 tools/build.py" >&2
  fi
  echo "" >&2
  exit 1
fi

# ── HOME hijack sandbox ───────────────────────────────────────
# $HERE/_home is a private HOME. $HERE/_home/.hermes is a symlink
# pointing to $HERE/data, so any library that reads or writes ~/.hermes
# (some plugins, etc.) lands inside the portable folder.
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
# Set PYTHONHOME for python-build-standalone (fixes "No module named encodings")
# Find the dir containing lib/python3.12 inside PYTHON_DIR
# Handles: install/ layout (old uv), cpython-3.12-xxx/ layout (new uv)
PYTHON_HOME=""
for _candidate in "$PYTHON_DIR"/*/install "$PYTHON_DIR"/install "$PYTHON_DIR"/* "$PYTHON_DIR"; do
  if [ -d "$_candidate/lib/python3.12" ] || [ -d "$_candidate/lib/python3.13" ] || [ -d "$_candidate/lib/python3.14" ]; then
    PYTHON_HOME="$_candidate"
    break
  fi
done
if [ -n "$PYTHON_HOME" ]; then
  export PYTHONHOME="$PYTHON_HOME"
fi
if [ -n "$NODE_DIR" ]; then
  export PATH="$VENV_DIR/bin:$NODE_DIR/bin:$PYTHON_DIR:$PATH"
else
  export PATH="$VENV_DIR/bin:$PYTHON_DIR:$PATH"
fi
cd "$HERE"

# ── Remove macOS quarantine (prevents "Killed" on unsigned binaries) ──
if command -v xattr >/dev/null 2>&1; then
  if xattr -lr "$HERE" 2>/dev/null | grep -qm1 "com.apple.quarantine"; then
    echo "  Removing macOS security restriction..."
    xattr -rd com.apple.quarantine "$HERE" 2>/dev/null || true
    echo "  Done"
  fi
fi

# ── Self-heal launcher shebangs ───────────────────────────────
# Same class of bug as Windows: if the portable zip was built on
# one machine and shebangs ended up absolute (or if mac-rebuild.sh
# just regenerated the venv at a new absolute path), they break
# when the folder moves. fix_shims.py rewrites them to the local
# python. Harmless (no-op) when shebangs are already `/bin/sh`-
# wrapped relocatable stubs, which is the common case on macOS.
# Kept in sync with Hermes.sh — previously only Hermes.sh ran this.
if [ -f "$HERE/lib/fix_shims.py" ]; then
  PORTABLE_PY=""
  # Prefer the real python-build-standalone binary (never a trampoline).
  for cand in "$PYTHON_DIR"/*/bin/python3.12 \
              "$PYTHON_DIR"/*/bin/python3 \
              "$VENV_DIR/bin/python"; do
    if [ -x "$cand" ]; then PORTABLE_PY="$cand"; break; fi
  done
  if [ -n "$PORTABLE_PY" ]; then
    "$PORTABLE_PY" "$HERE/lib/fix_shims.py" 2>/dev/null || true
  fi
fi

# ── Cleanup: must be reachable even after child exits ─────────
# OWN_LOCK gates the unlink: we only clear the lock file if WE were
# the process that created it. Without this guard, a second launch
# that correctly detects "already running" and exits 1 would still
# run the trap and delete the first instance's lock — making the
# single-instance check useless from the third launch onward.
HERMES_PID=""
CONFIG_PID=""
OWN_LOCK=0
cleanup() {
  # Kill watchdog first to prevent it from restarting config_server
  if [ -n "${WATCHDOG_PID:-}" ] && kill -0 "$WATCHDOG_PID" 2>/dev/null; then
    kill_tree "$WATCHDOG_PID"
  fi
  # Kill config server if still alive
  if [ -n "$CONFIG_PID" ] && kill -0 "$CONFIG_PID" 2>/dev/null; then
    kill_tree "$CONFIG_PID"
  fi
  # Kill hermes child if still alive (covers Ctrl-C from this script)
  if [ -n "$HERMES_PID" ] && kill -0 "$HERMES_PID" 2>/dev/null; then
    kill_tree "$HERMES_PID"
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


# ── Start Hermes Web UI (optional) ──────────────────────────────
# Check if Node.js is available and version >= 23
NODE_OK=false
if [ -n "$NODE_DIR" ] && [ -x "$NODE_DIR/bin/node" ]; then
  NODE_VER=$("$NODE_DIR/bin/node" -v 2>/dev/null | sed 's/v//' | cut -d. -f1)
  if [ -n "$NODE_VER" ] && [ "$NODE_VER" -ge 23 ] 2>/dev/null; then
    NODE_OK=true
  fi
fi
if [ "$NODE_OK" = "true" ]; then
  if command -v hermes-web-ui >/dev/null 2>&1 || [ -x "$NODE_DIR/bin/hermes-web-ui" ]; then
    echo "  Starting Hermes Web UI on port 8648..."
    hermes-web-ui start 8648 >/dev/null 2>&1 || true
    echo "  Hermes Web UI: http://127.0.0.1:8648"
  fi
else
  echo "  Hermes Web UI: skipped (Node.js >= 23 required)"
fi

# ── Desktop mode launch ────────────────────────────────────────
if [ "$LAUNCH_MODE" = "desktop" ]; then
  echo ""
  echo "  启动桌面版..."
  echo ""

  # 检查桌面版是否存在
  DESKTOP_APP=""
  if [ -d "$HERE/runtime/desktop/dist/mac-arm64/Hermes.app" ]; then
    DESKTOP_APP="$HERE/runtime/desktop/dist/mac-arm64/Hermes.app"
  elif [ -d "$HERE/runtime/desktop/dist/mac/Hermes.app" ]; then
    DESKTOP_APP="$HERE/runtime/desktop/dist/mac/Hermes.app"
  elif [ -x "$HERE/runtime/desktop/dist/linux-unpacked/Hermes" ]; then
    DESKTOP_APP="$HERE/runtime/desktop/dist/linux-unpacked/Hermes"
  fi

  if [ -z "$DESKTOP_APP" ]; then
    echo "  [ERROR] 桌面版未找到"
    echo ""
    echo "  请先构建桌面版:"
    echo "    python3 tools/build.py"
    echo ""
    exit 1
  fi

  # macOS: 检查桌面版二进制架构是否匹配
  if [ "$OS" = "Darwin" ] && command -v file >/dev/null 2>&1; then
    _APP_BIN=""
    # 从 Info.plist 读取可执行文件名
    _PLIST="$DESKTOP_APP/Contents/Info.plist"
    if [ -f "$_PLIST" ]; then
      _EXEC_NAME=$(/usr/libexec/PlistBuddy -c "Print :CFBundleExecutable" "$_PLIST" 2>/dev/null || true)
      if [ -n "$_EXEC_NAME" ] && [ -f "$DESKTOP_APP/Contents/MacOS/$_EXEC_NAME" ]; then
        _APP_BIN="$DESKTOP_APP/Contents/MacOS/$_EXEC_NAME"
      fi
    fi
    if [ -n "$_APP_BIN" ]; then
      _BIN_INFO="$(file -b "$_APP_BIN" 2>/dev/null || true)"
      case "$ARCH" in
        x86_64|amd64)
          if echo "$_BIN_INFO" | grep -q "arm64" && ! echo "$_BIN_INFO" | grep -qE "x86_64|universal"; then
            echo "  桌面版为 arm64 架构，当前 Mac 为 x86_64"
            echo "  回退到 CLI 模式（需要 Rosetta 2 或 arm64 Mac 才能运行桌面版）"
            echo ""
            LAUNCH_MODE="cli"
          fi
          ;;
        arm64|aarch64)
          if echo "$_BIN_INFO" | grep -q "x86_64" && ! echo "$_BIN_INFO" | grep -qE "arm64|universal"; then
            echo "  桌面版为 x86_64 架构，当前 Mac 为 arm64"
            echo "  回退到 CLI 模式"
            echo ""
            LAUNCH_MODE="cli"
          fi
          ;;
      esac
    fi
  fi
fi

# 桌面版正常启动（架构匹配）
if [ "$LAUNCH_MODE" = "desktop" ]; then
  export HERMES_DESKTOP_USER_DATA_DIR="$HERE/data/desktop-userdata"
  export HERMES_PORTABLE_ROOT="$HERE"
  export HERMES_PORTABLE_MODE="1"

  # 后台启动配置中心（端口 17520）
  export HERMES_BROWSER_OPENED=1
  nohup "$VENV_DIR/bin/python" "$HERE/lib/config_server.py" \
    > "$HERE/data/config_server.log" 2>&1 &
  CONFIG_PID=$!

  # Wait for Config Server to start
  echo "  Starting Config Server..."
  for i in $(seq 1 20); do
    sleep 0.5
    if curl -s -o /dev/null "http://127.0.0.1:17520/" 2>/dev/null; then
      echo "  Config Server ready"
      break
    fi
  done

  # Read Token from runtime.json
  TOKEN=""
  if [ -f "$HERE/data/runtime.json" ]; then
    TOKEN=$(python3 -c "
import json
from pathlib import Path
try:
    runtime = json.loads(Path('$HERE/data/runtime.json').read_text())
    print(runtime.get('configServerToken', ''))
except:
    pass
" 2>/dev/null)
  fi

  # Open browser with Token
  if [ -n "$TOKEN" ]; then
open_url() {
  if command -v open >/dev/null 2>&1; then open "$1"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$1"
  fi
}

    open_url "http://127.0.0.1:17520/#token=$TOKEN"
  else
    open_url "http://127.0.0.1:17520/"
  fi

  echo "  Config panel: http://127.0.0.1:17520"

  # 启动桌面版
  case "$DESKTOP_APP" in
    *.app) open "$DESKTOP_APP" ;;
    *)     exec "$DESKTOP_APP" "$@" ;;
  esac
  exit 0
fi

# ── First-run / --config handling ─────────────────────────────
HAS_KEY=false
if [ -f "$HERE/data/.env" ]; then
  if grep -qE '^[A-Z_]+_API_KEY=.{10,}' "$HERE/data/.env" 2>/dev/null; then
    HAS_KEY=true
  fi
fi



if [ "${1-}" = "--config" ] || [ "$HAS_KEY" = "false" ]; then
  echo ""
  echo "  Opening config panel at http://127.0.0.1:17520 ..."
  echo ""
  open_url "http://127.0.0.1:17520"
  # Tell config_server we already opened the browser, so it doesn't
  # open a second tab (see config_server.main).
  export HERMES_BROWSER_OPENED=1
  # Run in foreground; trap handlers still fire on exit.
  "$VENV_DIR/bin/python" "$HERE/lib/config_server.py"
  exit $?
fi

# ── Background config server with watchdog (auto-restart on crash) ──
CONFIG_PID=""
export HERMES_BROWSER_OPENED=1

start_config_server() {
  "$VENV_DIR/bin/python" "$HERE/lib/config_server.py" >/dev/null 2>&1 &
  CONFIG_PID=$!
}

MAX_RESTARTS=3
restart_count=0
MAX_RESTARTS=3

watchdog_config_server() {
  local parent_pid=$$
  while true; do
    sleep 10
    if ! kill -0 "$parent_pid" 2>/dev/null; then
      exit 0
    fi
    # Restart config_server if crashed
    if [ -n "$CONFIG_PID" ] && ! kill -0 "$CONFIG_PID" 2>/dev/null; then
      echo "  Config Server crashed. Restarting..."
      start_config_server
    fi
    # Restart hermes gateway if crashed (auto-restart)
    if [ -n "$HERMES_PID" ] && ! kill -0 "$HERMES_PID" 2>/dev/null; then
      if [ $restart_count -lt $MAX_RESTARTS ]; then
        restart_count=$((restart_count + 1))
        echo "  Hermes Gateway crashed. Restarting ($restart_count/$MAX_RESTARTS)..."
        "$VENV_DIR/bin/hermes" &
        HERMES_PID=$!
      else
        echo "  Hermes Gateway crashed $MAX_RESTARTS times. Giving up."
        exit 1
      fi
    fi
  done
}

start_config_server
watchdog_config_server &
WATCHDOG_PID=$!
echo "  Config panel: http://127.0.0.1:17520 (change model anytime)"

# ── Run hermes in foreground, BUT NOT with exec ───────────────
# exec would replace this shell and the EXIT trap would never fire,
# leaving the config server child orphaned. Use a normal child + wait.
"$VENV_DIR/bin/hermes" "$@" &
HERMES_PID=$!
wait "$HERMES_PID"
EXITCODE=$?
HERMES_PID=""
exit $EXITCODE
