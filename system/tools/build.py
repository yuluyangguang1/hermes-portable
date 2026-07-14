#!/usr/bin/env python3
"""
Hermes Portable — single-entry build script.

Produces a self-contained HermesPortable/ folder that can be copied to a
USB stick or any other machine (same OS/arch) and run without installing
anything on the host.

Usage:
  python3 build.py                        # build with desktop (default)
  python3 build.py --no-desktop           # build CLI only (no desktop)
  python3 build.py --layout universal     # universal layout (venv-<platform>/, python-<platform>/)
  python3 build.py /Volumes/U盘           # build into a specific location
  python3 build.py --output DIR

This is the *only* build script; there is no build_windows.py.
Windows is a first-class target of this same file.
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import zipfile
from datetime import datetime
from pathlib import Path

# ─── Windows: force UTF-8 on stdout/stderr ─────────────────────
# GitHub Actions' Windows runner defaults the Python stdout codec to
# cp1252, which cannot encode the box-drawing glyphs in our banner
# ("╦╠╩…"). This crashed the Windows build with UnicodeEncodeError
# before step_uv even started. Force UTF-8 for both streams.
# Safe on other platforms too — they're usually already UTF-8.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        # Older Pythons or non-text streams — ignore.
        pass

# ─── Config ────────────────────────────────────────────────────
HERMES_REPO = "https://github.com/NousResearch/hermes-agent.git"
HERMES_TAG = "v2026.7.1"  # v0.18.0 — The Judgment Release
PYTHON_VERSION = "3.12"
EXTRAS = "cron,messaging,cli,mcp,web,tts-premium"
# Node 24 LTS (active LTS until 2026-10, maintenance until 2028-04).
NODE_VERSION = "24.15.0"

# ─── ANSI colors ───────────────────────────────────────────────
G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
# Disable on Windows cmd that doesn't support ANSI
if platform.system() == "Windows" and not os.environ.get("WT_SESSION"):
    G = R = Y = C = B = X = ""

def log(tag, color, msg):
    print(f"{color}[{tag}]{X} {msg}")

def info(m): log("·", C, m)
def ok(m):   log("✓", G, m)
def warn(m): log("!", Y, m)
def fail(m): log("✗", R, m); sys.exit(1)

def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)

def download(url, dest):
    info(f"Downloading {url.split('/')[-1]} …")
    # --connect-timeout 30  : fail fast on dead mirrors / firewalled networks
    # --max-time 600        : 10-minute ceiling per file (uv/node/python each
    #                         < 150 MB; 10 min leaves plenty of headroom
    #                         even on slow links without letting a stuck
    #                         connection eat the workflow's 40-min quota)
    # --retry 3             : transient HTTP 5xx and network hiccups
    # --retry-delay 2       : small backoff between retries
    # Without these the build would silently hang for the full 40-minute
    # workflow timeout on a slow/unreachable mirror, which happened on
    # v0.12.x when the Node.js CDN was throttled.
    run([
        "curl", "-fSL",
        "--connect-timeout", "30",
        "--max-time", "600",
        "--retry", "3",
        "--retry-delay", "2",
        "-o", str(dest), url,
    ])

def detect_platform():
    """Return (system, arch, platform_label).

    platform_label matches what the launcher scripts look for:
      macos-arm64, macos-x64, linux-x64, linux-arm64, windows-x64, windows-arm64
    """
    system = platform.system()
    mach = platform.machine().lower()
    if mach in ("x86_64", "amd64"):
        arch = "x64"
    elif mach in ("aarch64", "arm64"):
        arch = "arm64"
    elif mach in ("i386", "i686", "x86"):
        arch = "x86"
    else:
        arch = mach

    if system == "Darwin":
        label = f"macos-{arch}"
    elif system == "Linux":
        fail("Linux is not supported in this build. Use macOS or Windows.")
    elif system == "Windows":
        label = f"windows-{arch}"
    else:
        label = f"{system.lower()}-{arch}"
    return system, arch, label

def banner(label):
    print(f"""
{B}{C}
  ╦ ╦╔═╗╦═╗╔═╗╔═╗╔═╗╔╦╗╔═╗
  ╠═╣╠═╣╠╦╝╠═╝║╣ ║   ║ ║ ║
  ╩ ╩╩ ╩╩╚═╩  ╚═╝╚═╝╩ ╩╚═╝{X}

  {B}Portable Builder{X}
  Target : {C}{label}{X}
  Python : {C}{PYTHON_VERSION}{X}
  Node.js: {C}{NODE_VERSION}{X}
""")

# ═══════════════════════════════════════════════════════════════
#  BUILD STEPS
# ═══════════════════════════════════════════════════════════════

def step_uv(ctx):
    """Copy or download uv into ROOT."""
    ROOT, system, arch, _ = ctx["ROOT"], ctx["system"], ctx["arch"], ctx["label"]
    uv_bin = ROOT / ("uv.exe" if system == "Windows" else "uv")
    if uv_bin.exists():
        ok("uv already present"); return

    system_uv = shutil.which("uv")
    if system_uv:
        info(f"Copying uv from {system_uv}")
        shutil.copy2(system_uv, uv_bin)
        if system != "Windows":
            uv_bin.chmod(0o755)
        ok("uv ready (from system)")
        return

    # uv release URL naming
    uv_arch = {"x64": "x86_64", "arm64": "aarch64", "x86": "i686"}.get(arch, arch)
    if system == "Darwin":
        url = f"https://github.com/astral-sh/uv/releases/latest/download/uv-{uv_arch}-apple-darwin.tar.gz"

    else:  # Windows
        url = f"https://github.com/astral-sh/uv/releases/latest/download/uv-{uv_arch}-pc-windows-msvc.zip"

    archive = ROOT / "_uv_tmp"
    download(url, archive)
    if system == "Windows":
        with zipfile.ZipFile(archive) as z:
            for n in z.namelist():
                if n.endswith("uv.exe"):
                    (ROOT / "uv.exe").write_bytes(z.read(n))
                    break
    else:
        with tarfile.open(archive, "r:gz") as t:
            for m in t.getmembers():
                if m.name.endswith("/uv") or m.name == "uv":
                    f = t.extractfile(m)
                    uv_bin.write_bytes(f.read())
                    break
    archive.unlink(missing_ok=True)
    if system != "Windows":
        uv_bin.chmod(0o755)
    ok("uv ready")


def step_python(ctx):
    """Install relocatable Python via uv."""
    ROOT, system = ctx["ROOT"], ctx["system"]
    py_dir = ROOT / ctx["python_name"]
    uv = ROOT / ("uv.exe" if system == "Windows" else "uv")

    # Already installed?
    for pattern in ("python3*", "python.exe", "python3.exe"):
        if any(py_dir.rglob(pattern)):
            ok("Python already present"); return

    py_dir.mkdir(parents=True, exist_ok=True)
    info(f"Installing Python {PYTHON_VERSION} …")
    env = os.environ.copy()
    env["UV_PYTHON_INSTALL_DIR"] = str(py_dir)
    try:
        run([str(uv), "python", "install", PYTHON_VERSION, "--install-dir", str(py_dir)], env=env)
        ok(f"Python {PYTHON_VERSION} installed")
    except subprocess.CalledProcessError:
        fail(
            "uv python install failed. Cannot create a portable Python.\n"
            "  • Ensure internet access is available during build.\n"
            "  • System-Python copies are NOT portable across machines\n"
            "    (symlinks + hardcoded paths in pyvenv.cfg break)."
        )


def _find_python(ctx):
    """Locate the python executable inside the portable python dir."""
    py_dir = ctx["ROOT"] / ctx["python_name"]
    candidates = (
        "python3.12", "python3", "python",
        "python3.12.exe", "python3.exe", "python.exe",
    )
    for root, _, files in os.walk(py_dir):
        for f in files:
            if f in candidates:
                p = Path(root) / f
                if p.is_file():
                    return p
    fail("Cannot find python binary inside portable python dir")


def _clean_hermes_src(src):
    for d in src.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)
    for f in src.rglob("*.pyc"):
        f.unlink(missing_ok=True)
    for pat in ("RELEASE_*.md",):
        for f in src.glob(pat):
            f.unlink(missing_ok=True)
    # Drop the .git metadata from the cloned hermes-agent. Reasons:
    #   * it can be 10-50 MB (depth=1 helps but isn't zero),
    #   * it bakes the clone URL and the build-time machine's git
    #     config into the zip we ship to users,
    #   * update.py specifically checks (hermes-agent / ".git").exists()
    #     to decide "updatable vs frozen" — we intentionally want shipped
    #     zips to say "not a git clone, run rebuild" instead of pretending
    #     they can `git pull` (on a --depth=1 shallow clone that will
    #     often fail mysteriously).
    git_dir = src / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir, ignore_errors=True)
    for name in ("docs", "docker", "datagen-config-examples",
                 ".pytest_cache", ".github", ".vscode", ".idea"):
        d = src / name
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
    for name in ("Dockerfile", "flake.lock", "flake.nix"):
        f = src / name
        if f.exists():
            f.unlink(missing_ok=True)


def step_hermes(ctx):
    ROOT = ctx["ROOT"]
    src = ROOT / "hermes-agent"
    if src.exists() and (src / "run_agent.py").exists():
        ok("hermes-agent present"); return

    local_src = Path.home() / ".hermes" / "hermes-agent"
    if local_src.exists() and (local_src / "run_agent.py").exists():
        info("Copying hermes-agent from ~/.hermes/ …")
        shutil.copytree(local_src, src, ignore=shutil.ignore_patterns(
            "__pycache__", ".git", "node_modules", "venv", "*.pyc",
            "tests", ".pytest_cache", "*.egg-info",
            "docs", "docker", "Dockerfile", "flake.*",
            "RELEASE_*.md", "datagen-config-examples",
            ".github", ".vscode", ".idea",
        ))
        ok("hermes-agent copied from local")
        return

    info("Cloning hermes-agent from GitHub …")
    try:
        run(["git", "clone", "--depth", "1", "--branch", HERMES_TAG, HERMES_REPO, str(src)])
        _clean_hermes_src(src)
        ok("hermes-agent cloned")
    except subprocess.CalledProcessError:
        fail("Cannot clone hermes-agent. Check internet connection, "
             "or ensure ~/.hermes/hermes-agent exists.")


def step_venv(ctx):
    """Create venv via `uv venv` (relocatable) and install deps non-editable."""
    ROOT, system = ctx["ROOT"], ctx["system"]
    venv = ROOT / ctx["venv_name"]
    uv = ROOT / ("uv.exe" if system == "Windows" else "uv")
    src = ROOT / "hermes-agent"
    py = _find_python(ctx)

    if not venv.exists():
        info("Creating virtual environment via uv (relocatable) …")
        run([str(uv), "venv", str(venv), "--python", str(py), "--relocatable"])
        ok("venv created")

    py_venv = (venv / "Scripts" / "python.exe") if system == "Windows" \
        else (venv / "bin" / "python")

    # Fix permissions on venv binaries
    bin_dir = venv / ("Scripts" if system == "Windows" else "bin")
    if bin_dir.exists():
        for f in bin_dir.iterdir():
            if f.is_file() and not f.suffix:
                try: f.chmod(0o755)
                except Exception: pass
        ok("Fixed venv binary permissions")

    info(f"Installing hermes-agent[{EXTRAS}] (non-editable) …")
    # IMPORTANT: no `-e` flag. editable installs write absolute paths into
    # site-packages/*.pth and break the moment the folder moves (USB key
    # drive letter changes, /Volumes/USB name changes, etc.).
    try:
        run([str(uv), "pip", "install", f"{src}[{EXTRAS}]",
             "--python", str(py_venv)])
    except subprocess.CalledProcessError:
        warn("Full extras failed, falling back to core …")
        run([str(uv), "pip", "install", str(src),
             "--python", str(py_venv)])
    ok("Dependencies installed")


def step_data(ctx):
    ROOT = ctx["ROOT"]
    data = ROOT / "data"
    for d in ("sessions", "skills", "logs", "memories", "cron",
              "plugins", "audio_cache", "image_cache", "checkpoints"):
        (data / d).mkdir(parents=True, exist_ok=True)

    envf = data / ".env"
    if not envf.exists():
        envf.write_text(
            "# ═══════════════════════════════════════════\n"
            "#  Hermes Portable — API Keys\n"
            "#  Uncomment ONE provider and paste your key.\n"
            "# ═══════════════════════════════════════════\n\n"
            "# OPENROUTER_API_KEY=sk-or-v1-...\n"
            "# ANTHROPIC_API_KEY=sk-ant-...\n"
            "# OPENAI_API_KEY=sk-...\n"
            "# DEEPSEEK_API_KEY=...\n"
            "# GOOGLE_API_KEY=...\n",
            encoding="utf-8",
        )
    cfg = data / "config.yaml"
    if not cfg.exists():
        cfg.write_text(
            "# Hermes Portable — Configuration\n"
            "model:\n"
            "  default: \"openrouter/anthropic/claude-sonnet-4\"\n"
            "  provider: \"openrouter\"\n\n"
            "terminal:\n"
            "  backend: \"local\"\n"
            "  timeout: 180\n\n"
            "compression:\n"
            "  enabled: true\n"
            "  threshold: 0.50\n"
            "  target_ratio: 0.20\n\n"
            "display:\n"
            "  skin: \"default\"\n"
            "  tool_progress: true\n"
            "  show_cost: true\n\n"
            "memory:\n"
            "  memory_enabled: true\n"
            "  user_profile_enabled: true\n",
            encoding="utf-8",
        )
    ok("data/ ready")


def step_nodejs(ctx):
    ROOT, system, arch = ctx["ROOT"], ctx["system"], ctx["arch"]
    node_dir = ROOT / ctx["node_name"]
    exe = "node.exe" if system == "Windows" else "node"
    if node_dir.exists() and any(node_dir.rglob(exe)):
        ok("Node.js already present"); return

    # Node.js uses x64 / arm64 (same as our label suffixes).
    node_arch = {"x64": "x64", "arm64": "arm64"}.get(arch, arch)
    if system == "Darwin":
        url = f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-darwin-{node_arch}.tar.gz"

    elif system == "Windows":
        # Node.js v24+ does ship Windows arm64 prebuilt, but the launcher
        # bat file currently only knows about x64; sticking with x64 keeps
        # behavior identical on ARM hardware (runs under Prism emulation,
        url = f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-win-x64.zip"
    else:
        warn(f"Unsupported system for Node.js fetch: {system}"); return

    archive = ROOT / "_node_tmp"
    try:
        download(url, archive)
    except subprocess.CalledProcessError as e:
        warn(f"Node.js download failed ({e.returncode}); skipping.")
        warn(f"  URL: {url}")
        return
    node_dir.mkdir(parents=True, exist_ok=True)

    if system == "Windows":
        with zipfile.ZipFile(archive) as z:
            z.extractall(node_dir)
        nested = node_dir / f"node-v{NODE_VERSION}-win-x64"
        if nested.exists():
            for item in nested.iterdir():
                shutil.move(str(item), str(node_dir / item.name))
            nested.rmdir()
    else:
        with tarfile.open(archive, "r:gz") as t:
            # Filter out unsafe entries (path traversal), but allow symlinks
            # whose target stays within the archive when resolved relative
            # to the symlink's own directory. Node.js tarballs ship
            # bin/npm → ../lib/node_modules/npm/bin/npm-cli.js; naive
            # rejection of anything containing '..' loses npm/npx/corepack,
            import posixpath
            safe = []
            for m in t.getmembers():
                n = m.name
                if n.startswith("/") or ".." in n.split("/"):
                    continue
                if m.issym() or m.islnk():
                    target = m.linkname
                    if target.startswith("/"):
                        continue
                    # Resolve the symlink target relative to the symlink's
                    # own parent directory, then check it stays inside
                    # the archive root.
                    link_dir = posixpath.dirname(n)
                    resolved = posixpath.normpath(posixpath.join(link_dir, target))
                    if resolved.startswith("..") or resolved.startswith("/"):
                        continue
                safe.append(m)
            t.extractall(node_dir, members=safe)
        # Nested dir name differs per platform; handle both forms.
        nested = node_dir / f"node-v{NODE_VERSION}-{system.lower()}-{node_arch}"
        if nested.exists():
            for item in nested.iterdir():
                shutil.move(str(item), str(node_dir / item.name))
            nested.rmdir()
        bin_dir = node_dir / "bin"
        if bin_dir.exists():
            for f in bin_dir.iterdir():
                try: f.chmod(0o755)
                except Exception: pass

    archive.unlink(missing_ok=True)

    # Verify node / npm / npx actually made it out of the archive.
    # This is cheap defense-in-depth: if any future change (tarfile
    # filter, flatten logic, mirror hiccup) ever loses one of them
    # again, fail the build immediately rather than silently shipping
    # a zip without a working Web UI (as v0.13.0-0.13.3 did).
    # Inspired by @KESHAOYE's PR #4.
    if system == "Windows":
        required = [node_dir / "node.exe", node_dir / "npm.cmd", node_dir / "npx.cmd"]
    else:
        required = [node_dir / "bin" / "node", node_dir / "bin" / "npm", node_dir / "bin" / "npx"]
    missing = [p for p in required if not p.exists()]
    if missing:
        fail("Node.js extraction incomplete — missing:\n  "
             + "\n  ".join(str(p) for p in missing))

    ok(f"Node.js v{NODE_VERSION} ready")

    # Install hermes-web-ui globally
    npm = node_dir / "bin" / "npm" if system != "Windows" else node_dir / "npm.cmd"
    if npm.exists():
        info("Installing hermes-web-ui...")
        try:
            subprocess.run(
                [str(npm), "install", "-g", "hermes-web-ui"],
                capture_output=True, text=True, timeout=120,
                env={**ctx.get("env", {}), "PATH": str(node_dir / "bin") + ":" + ctx.get("env", {}).get("PATH", "")}
            )
            ok("hermes-web-ui installed")
        except Exception as e:
            warn(f"hermes-web-ui install failed: {e}")


# Files that must be *copied verbatim* from the repo into the portable folder.
# This is the single source of truth — no more inlined bat/sh strings.
# Paths are relative to the repo root. Directory structure is preserved
# in the dist (e.g. "system/lib/config_server.py" → ROOT/lib/config_server.py).
_STATIC_ASSETS = [
    # Launchers (root — user-facing)
    "Hermes.command",
    "Hermes.bat",
    "HermesPortable使用说明.html",
    # runtime/ — all system files
    "system/lib/config_server.py",
    "system/lib/chat_viewer.py",
    "system/lib/update.py",
    "system/lib/update.sh",
    "system/lib/fix_shims.py",
    "system/tools/build.py",
    "system/tools/mac-rebuild.sh",
]


def step_launchers(ctx):
    ROOT = ctx["ROOT"]
    repo = Path(__file__).parent.parent.parent  # system/tools/ -> repo root
    for fname in _STATIC_ASSETS:
        src = repo / fname
        if not src.exists():
            warn(f"missing in repo: {fname}")
            continue
        # Put system files in runtime/ subfolder
        if fname.startswith("system/"):
            dst = ROOT / "runtime" / fname[7:]  # Remove "system/" prefix
        else:
            dst = ROOT / fname
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        # executable bits for unix launchers / scripts
        if fname.endswith((".sh", ".command")):
            try: dst.chmod(0o755)
            except Exception: pass
    ok("Launchers + runtime/ copied from repo")


def step_cleanup(ctx):
    ROOT = ctx["ROOT"]
    info("Cleaning build artifacts …")
    removed = 0
    for d in ROOT.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True); removed += 1
    for f in ROOT.rglob("*.pyc"):
        f.unlink(missing_ok=True); removed += 1
    for f in ROOT.rglob(".DS_Store"):
        f.unlink(missing_ok=True); removed += 1
    for d in ROOT.rglob("*.egg-info"):
        shutil.rmtree(d, ignore_errors=True); removed += 1
    # Trim site-packages tests. Restrict this to *top-level* `tests/`
    # (and `test/`) directly under each installed package — we can't
    # `rglob("tests")` because some packages (numpy.tests,
    # tornado.tests, hypothesis.tests) ship real runtime submodules
    # under that name and blowing them away breaks imports. The
    # top-level package directory itself is never actually named
    # `tests` unless the user did something strange, so targeting just
    # `site-packages/*/tests/` is safe and still recovers most of the
    # weight (pytest, numpy's test-data fixtures, etc.).
    venv = ROOT / ctx["venv_name"]
    if venv.exists():
        lib = "Lib" if ctx["system"] == "Windows" else "lib"
        site = venv / lib / f"python{PYTHON_VERSION}" / "site-packages"
        if site.exists():
            # Known-safe top-level test dirs: strip conservatively.
            # Keep the list in sync with what ships by default in the
            # EXTRAS set above; don't add packages whose `tests` module
            # is importable.
            for pkg in site.iterdir():
                if not pkg.is_dir():
                    continue
                for name in ("tests", "test"):
                    t = pkg / name
                    # Only delete if it has no __init__.py at all — with
                    # an __init__.py it's an importable submodule and
                    # removing it will break `from pkg.tests import ...`
                    # at runtime.
                    if t.is_dir() and not (t / "__init__.py").exists():
                        shutil.rmtree(t, ignore_errors=True)
                        removed += 1
            # npm-style node_modules test dirs are safe to wipe — JS
            # packages don't import their own tests at runtime.
            for d in site.rglob("__tests__"):
                shutil.rmtree(d, ignore_errors=True); removed += 1
    # Fix permissions on all binaries in venv
    if venv.exists():
        bin_dir = venv / ("Scripts" if ctx["system"] == "Windows" else "bin")
        if bin_dir.exists():
            for f in bin_dir.iterdir():
                if f.is_file():
                    try: f.chmod(0o755)
                    except Exception: pass
            ok("Fixed venv binary permissions")

    ok(f"Cleaned {removed} artifacts")


def step_readme(ctx):
    ROOT = ctx["ROOT"]
    label = ctx["label"]
    venv_name = ctx["venv_name"]
    (ROOT / "README.txt").write_text(
        "Hermes Portable\n"
        "===============\n\n"
        f"  Built for : {label}\n"
        f"  Build time: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"  venv dir  : {venv_name}/\n"
        "\n"
        "How to run\n"
        "----------\n"
        "  macOS    →  double-click  Hermes.command\n"

        "  Windows  →  double-click  Hermes.bat\n"
        "\n"
        "First run opens a config panel at http://127.0.0.1:17520 for\n"
        "you to paste an API key. After that it launches Hermes directly.\n"
        "\n"
        "macOS: first double-click shows 'permission denied' / '您没有权限'\n"
        "-----------------------------------------------------------------\n"
        "  macOS tags anything downloaded via a browser with a Gatekeeper\n"
        "  quarantine flag. Unsigned scripts (Hermes.command) won't run\n"
        "  until you clear it once. Open Terminal and run:\n"
        "\n"
        "    cd /path/to/HermesPortable     # drag the folder into Terminal\n"
        "    xattr -cr . && chmod +x Hermes.command Hermes.sh\n"
        "\n"
        "  Then double-click Hermes.command normally. You only do this\n"
        "  once per download.\n"
        "\n"
        "Windows notes\n"
        "-------------\n"
        "  • Windows native support is stable (upstream Hermes Agent docs\n"
        "    removed the Beta tag at v0.14.0). The launcher runs hermes\n"
        "    directly via venv\\Scripts\\hermes.exe — no WSL required.\n"
        "  • SmartScreen will warn \"Unknown publisher\" on first run.\n"
        "    Click \"More info\" → \"Run anyway\".\n"
        "  • Hermes-WSL.bat is still shipped as an optional path: use it if\n"
        "    you want POSIX-only features (e.g. dashboard's embedded /chat\n"
        "    terminal pane, which needs a POSIX PTY) or if your machine\n"
        "    blocks something the native path needs.\n"
        "  • Long paths (>260 chars) can break Python package loading;\n"
        "    prefer a short path like C:\\HP or D:\\HP.\n"
        "\n"
        "Universal zip\n"
        "-------------\n"
        "  The Universal zip contains venv-<platform>/ and python-<platform>/\n"
        "  dirs for macOS and Windows. Each launcher auto-picks the\n"
        "  right one; you don't need to do anything.\n"
        "\n"
        "Data\n"
        "----\n"
        "  data/             all user state (sessions / skills / logs)\n"
        "  data/.env         API keys\n"
        "  data/config.yaml  settings\n"
        "\n"
        "Update\n"
        "------\n"
        "  Open the config panel → bottom right → Check for Updates.\n"
        "  Or from a terminal:\n"
        "    python lib/update.py update\n",
        encoding="utf-8",
    )
    ok("README.txt written")


# ═══════════════════════════════════════════════════════════════
#  DESKTOP DOWNLOAD (pre-built)
# ═══════════════════════════════════════════════════════════════

# Official pre-built desktop app URLs
DESKTOP_URLS = {
    "Darwin": {
        "arm64": "https://hermes-assets.nousresearch.com/Hermes-Setup.dmg",
        "x64": "https://hermes-assets.nousresearch.com/Hermes-Setup.dmg",
    },
    "Windows": {
        "x64": "https://hermes-assets.nousresearch.com/Hermes-Setup.exe",
    },
    # Linux: no official desktop app yet — step_desktop() skips gracefully
}


def step_desktop(ctx):
    """Download and package the official pre-built Hermes Desktop app."""
    ROOT, system, arch = ctx["ROOT"], ctx["system"], ctx["arch"]
    runtime_dir = ROOT / "runtime" / "desktop"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # Get download URL
    system_urls = DESKTOP_URLS.get(system)
    if not system_urls:
        warn(f"No desktop app available for {system}")
        return

    url = system_urls.get(arch)
    if not url:
        warn(f"No desktop app available for {system}/{arch}")
        return

    info(f"Downloading Hermes Desktop for {system}/{arch} …")

    if system == "Darwin":
        _download_macos_desktop(url, runtime_dir)
    elif system == "Windows":
        _download_windows_desktop(url, runtime_dir)


    ok("Desktop app ready")


def _download_macos_desktop(url, runtime_dir):
    """Download and extract macOS .dmg"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        dmg_path = Path(tmp) / "Hermes.dmg"
        download(url, dmg_path)

        info("Extracting from DMG …")
        mount_point = Path(tmp) / "mount"
        mount_point.mkdir()

        # Mount DMG
        run(["hdiutil", "attach", str(dmg_path),
             "-mountpoint", str(mount_point),
             "-nobrowse", "-quiet"])

        try:
            # Find .app bundle
            for item in mount_point.iterdir():
                if item.suffix == ".app":
                    # Place under dist/ matching what launchers expect:
                    #   runtime/desktop/dist/mac-arm64/Hermes.app  (macOS arm64)
                    #   runtime/desktop/dist/mac/Hermes.app         (macOS x64)
                    import platform as _plat
                    arch = _plat.machine()
                    if arch == "arm64":
                        dest_dir = runtime_dir / "dist" / "mac-arm64"
                    else:
                        dest_dir = runtime_dir / "dist" / "mac"
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dst = dest_dir / item.name
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(item, dst)
                    info(f"  Extracted: {dst.relative_to(runtime_dir)}")
                    break
        finally:
            # Unmount DMG
            run(["hdiutil", "detach", str(mount_point), "-quiet"])


def _download_windows_desktop(url, runtime_dir):
    """Skip Windows desktop bundling — installer is a web downloader.

    The official Hermes Desktop Windows installer (~7 MB) is a web installer
    that downloads the real app at install time.  It cannot be extracted
    offline and hangs in headless/CI environments.  Users install the desktop
    app separately; Hermes.bat falls back to CLI mode until then.
    """
    warn("Windows desktop app is a web installer and cannot be bundled.")
    warn("Users can install it manually: https://hermes.nousresearch.com")
    warn("Hermes.bat will use CLI mode until the desktop app is installed.")


def _download_linux_desktop(url, runtime_dir):
    """Download Linux AppImage to dist/ (what launchers expect)"""
    dist_dir = runtime_dir / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    appimage_path = dist_dir / "Hermes.AppImage"
    download(url, appimage_path)
    appimage_path.chmod(0o755)
    info(f"  Downloaded: dist/{appimage_path.name}")


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

STEPS = [
    ("Downloading uv",               step_uv),
    ("Installing portable Python",   step_python),
    ("Cloning hermes-agent",         step_hermes),
    ("Creating venv + deps",         step_venv),
    ("Setting up data/",             step_data),
    ("Downloading Node.js",          step_nodejs),
    ("Copying launchers",            step_launchers),
    ("Writing README",               step_readme),
    ("Cleaning",                     step_cleanup),
]

STEPS_DESKTOP = [
    ("Building Desktop app",         step_desktop),
]


def parse_args():
    p = argparse.ArgumentParser(description="Build Hermes Portable")
    p.add_argument("--layout", choices=("platform", "universal"), default="platform",
                   help="'platform' puts deps in venv/python (default); "
                        "'universal' puts deps in venv-<platform>/python-<platform>/ "
                        "so multiple builds can be merged into one USB package.")
    p.add_argument("--output", "-o", default=None,
                   help="Output directory (default: dist/HermesPortable)")
    p.add_argument("--no-desktop", action="store_true",
                   help="Skip building the official Hermes Desktop app (desktop is built by default)")
    p.add_argument("positional", nargs="?", default=None,
                   help="Alias for --output (kept for backwards compatibility)")
    return p.parse_args()


def main():
    args = parse_args()
    system, arch, label = detect_platform()
    banner(label)

    # Compute output root
    out = args.output or args.positional
    if out:
        ROOT = Path(out).resolve()
        if ROOT.name != "HermesPortable":
            ROOT = ROOT / "HermesPortable"
    else:
        ROOT = Path(__file__).parent.parent.parent / "dist" / "HermesPortable"
    ROOT.mkdir(parents=True, exist_ok=True)

    # Platform-first layout: runtime/<platform>/{venv,python,node}
    if args.layout == "universal":
        venv_name = f"runtime/{label}/venv"
        python_name = f"runtime/{label}/python"
        node_name = f"runtime/{label}/node"
    else:
        venv_name = "runtime/venv"
        python_name = "runtime/python"
        node_name = "runtime/node"

    ctx = {
        "ROOT": ROOT,
        "system": system,
        "arch": arch,
        "label": label,
        "venv_name": venv_name,
        "python_name": python_name,
        "node_name": node_name,
    }

    info(f"Output : {ROOT}")
    info(f"Layout : {args.layout}")
    info(f"Desktop: {'no' if args.no_desktop else 'yes (default)'}")
    print()

    # Combine steps; desktop is built by default unless --no-desktop
    all_steps = STEPS[:]
    if not args.no_desktop:
        all_steps.extend(STEPS_DESKTOP)

    for i, (desc, fn) in enumerate(all_steps, 1):
        print(f"{B}[{i}/{len(all_steps)}] {desc}{X}")
        try:
            fn(ctx)
        except subprocess.CalledProcessError as e:
            print(f"  cmd={e.cmd}", file=sys.stderr)
            fail(f"Step '{desc}' failed with exit code {e.returncode}")
        except SystemExit:
            raise
        except Exception as e:
            import traceback; traceback.print_exc()
            fail(f"Step '{desc}' failed: {e}")
        print()

    total_bytes = sum(f.stat().st_size for f in ROOT.rglob("*") if f.is_file())
    print(f"{G}{B}  ✓ Build complete{X}")
    print(f"  Location: {C}{ROOT}{X}")
    print(f"  Size    : {C}{total_bytes / 1e6:.0f} MB{X}")
    if not args.no_desktop:
        print(f"  Desktop : {C}runtime/desktop/{X}")
    print(f"  Launchers: {C}Hermes.command / Hermes.sh / Hermes.bat{X}\n")


if __name__ == "__main__":
    main()
