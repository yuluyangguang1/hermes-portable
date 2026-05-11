#!/usr/bin/env python3
"""
Hermes Portable — single-entry build script.

Produces a self-contained HermesPortable/ folder that can be copied to a
USB stick or any other machine (same OS/arch) and run without installing
anything on the host.

Usage:
  python3 build.py                        # platform-only layout → dist/HermesPortable/
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
PYTHON_VERSION = "3.12"
EXTRAS = "cron,messaging,cli,mcp,web,tts-premium"
NODE_VERSION = "22.16.0"

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
    run(["curl", "-fSL", "-o", str(dest), url])

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
        label = f"linux-{arch}"
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
    elif system == "Linux":
        url = f"https://github.com/astral-sh/uv/releases/latest/download/uv-{uv_arch}-unknown-linux-gnu.tar.gz"
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
        run(["git", "clone", "--depth", "1", HERMES_REPO, str(src)])
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
    elif system == "Linux":
        # Prebuilt Linux tarballs require glibc ≥ 2.28 (verified by node's
        # release notes for v22.x). On older hosts the binary will fail
        # with GLIBC_2.xx-not-found — that's a target-side issue we can't
        # paper over here; document it in README.txt instead.
        url = f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-linux-{node_arch}.tar.gz"
    elif system == "Windows":
        # Node.js does not ship Windows arm64 prebuilt; use x64 under emulation.
        url = f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-win-x64.zip"
    else:
        warn(f"Unsupported system for Node.js fetch: {system}"); return

    archive = ROOT / "_node_tmp"
    try:
        download(url, archive)
    except subprocess.CalledProcessError as e:
        warn(f"Node.js download failed ({e.returncode}); skipping web UI.")
        warn(f"  URL: {url}")
        warn("  hermes-web-ui will not be bundled. You can install it later:")
        warn("    npm install -g hermes-web-ui")
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
    elif system == "Linux":
        with tarfile.open(archive, "r:gz") as t:
            safe = []
            for m in t.getmembers():
                n = m.name
                if n.startswith("/") or ".." in n.split("/"):
                    continue
                if m.issym() or m.islnk():
                    # Only accept symlinks that stay inside the archive
                    target = m.linkname
                    if target.startswith("/") or ".." in target.split("/"):
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
    # macos
    else:
        run(["tar", "-xzf", str(archive), "-C", str(node_dir)])

        # Nested dir name differs per platform; handle both forms.
        nested = node_dir / f"node-v{NODE_VERSION}-{system.lower()}-{node_arch}"
        if not nested.exists() and system == "Darwin":
            nested = node_dir / f"node-v{NODE_VERSION}-darwin-{node_arch}"

        if nested.exists():
            for item in nested.iterdir():
                target = node_dir / item.name
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                shutil.move(str(item), str(target))
            nested.rmdir()

        bin_dir = node_dir / "bin"
        if bin_dir.exists():
            for f in bin_dir.iterdir():
                try:
                    f.chmod(0o755)
                except Exception:
                    pass

        # Verify Node/npm/npx
        node_bin = node_dir / "bin" / "node"
        npm_bin = node_dir / "bin" / "npm"
        npx_bin = node_dir / "bin" / "npx"

        if not node_bin.exists():
            fail(f"node missing after extraction: {node_bin}")
        if not npm_bin.exists():
            fail(f"npm missing after extraction: {npm_bin}")
        if not npx_bin.exists():
            fail(f"npx missing after extraction: {npx_bin}") 

    archive.unlink(missing_ok=True)
    ok(f"Node.js v{NODE_VERSION} ready")


def step_webui(ctx):
    ROOT, system = ctx["ROOT"], ctx["system"]
    node_dir = ROOT / ctx["node_name"]
    if system == "Windows":
        npm = node_dir / "npm.cmd"
    else:
        npm = node_dir / "bin" / "npm"
    if not npm.exists():
        warn("npm not found; skipping hermes-web-ui install"); return

    # Already installed?
    if system == "Windows":
        webui_bin = node_dir / "hermes-web-ui.cmd"
    else:
        webui_bin = node_dir / "bin" / "hermes-web-ui"
    if webui_bin.exists():
        ok("hermes-web-ui already installed"); return

    info("Installing hermes-web-ui …")
    env = os.environ.copy()
    bin_path = node_dir / ("" if system == "Windows" else "bin")
    env["PATH"] = str(bin_path) + os.pathsep + env.get("PATH", "")
    try:
        run([str(npm), "install", "-g", "hermes-web-ui",
             "--prefix", str(node_dir)], env=env)
        ok("hermes-web-ui installed")
    except subprocess.CalledProcessError:
        warn("hermes-web-ui install failed; launcher will skip it gracefully")


# Files that must be *copied verbatim* from the repo into the portable folder.
# This is the single source of truth — no more inlined bat/sh strings.
_STATIC_ASSETS = [
    "config_server.py",
    "chat_viewer.py",
    "update.py",
    "update.sh",
    "guide.html",
    "favicon.svg",
    "HermesPortable使用说明.html",
    # Launchers
    "Hermes.command",
    "Hermes.sh",
    "Hermes.bat",
    "Hermes-WSL.bat",
    # Rebuild helpers — shipped so a user who carried a macOS-built zip
    # onto a Linux box can rebuild the runtime without re-downloading.
    "build.py",
    "linux-rebuild.sh",
]


def step_launchers(ctx):
    ROOT = ctx["ROOT"]
    repo = Path(__file__).parent
    for fname in _STATIC_ASSETS:
        src = repo / fname
        if not src.exists():
            warn(f"missing in repo: {fname}")
            continue
        dst = ROOT / fname
        shutil.copy2(src, dst)
        # executable bits for unix launchers / scripts
        if fname.endswith((".sh", ".command")):
            try: dst.chmod(0o755)
            except Exception: pass
    ok("Launchers copied from repo")


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
    # Trim site-packages tests
    venv = ROOT / ctx["venv_name"]
    if venv.exists():
        lib = "Lib" if ctx["system"] == "Windows" else "lib"
        site = venv / lib / f"python{PYTHON_VERSION}" / "site-packages"
        if site.exists():
            for d in site.rglob("tests"):
                if d.is_dir():
                    shutil.rmtree(d, ignore_errors=True); removed += 1
            for d in site.rglob("__tests__"):
                shutil.rmtree(d, ignore_errors=True); removed += 1
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
        "  Linux    →  ./Hermes.sh  (from a terminal)\n"
        "  Windows  →  double-click  Hermes.bat\n"
        "\n"
        "First run opens a config panel at http://127.0.0.1:17520 for\n"
        "you to paste an API key. After that it launches Hermes directly.\n"
        "\n"
        "Windows notes\n"
        "-------------\n"
        "  • Native Windows support is Early Beta. If you hit issues, try\n"
        "    Hermes-WSL.bat (requires WSL2 + a Linux venv in the folder).\n"
        "  • SmartScreen will warn \"Unknown publisher\" on first run.\n"
        "    Click \"More info\" → \"Run anyway\".\n"
        "  • Long paths (>260 chars) can break Python package loading;\n"
        "    prefer a short path like C:\\HP or D:\\HP.\n"
        "\n"
        "Universal zip\n"
        "-------------\n"
        "  The Universal zip contains venv-<platform>/ and python-<platform>/\n"
        "  dirs for macOS, Linux, and Windows. Each launcher auto-picks the\n"
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
        "    python update.py update\n",
        encoding="utf-8",
    )
    ok("README.txt written")


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
    ("Installing hermes-web-ui",     step_webui),
    ("Copying launchers",            step_launchers),
    ("Writing README",               step_readme),
    ("Cleaning",                     step_cleanup),
]


def parse_args():
    p = argparse.ArgumentParser(description="Build Hermes Portable")
    p.add_argument("--layout", choices=("platform", "universal"), default="platform",
                   help="'platform' puts deps in venv/python (default); "
                        "'universal' puts deps in venv-<platform>/python-<platform>/ "
                        "so multiple builds can be merged into one USB package.")
    p.add_argument("--output", "-o", default=None,
                   help="Output directory (default: dist/HermesPortable)")
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
        ROOT = Path(__file__).parent / "dist" / "HermesPortable"
    ROOT.mkdir(parents=True, exist_ok=True)

    # Platform-suffixed dir names for universal layout
    if args.layout == "universal":
        venv_name = f"venv-{label}"
        python_name = f"python-{label}"
        node_name = f"node-{label}"
    else:
        venv_name = "venv"
        python_name = "python"
        node_name = "node"

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
    print()

    for i, (desc, fn) in enumerate(STEPS, 1):
        print(f"{B}[{i}/{len(STEPS)}] {desc}{X}")
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
    print(f"  Launchers: {C}Hermes.command / Hermes.sh / Hermes.bat{X}\n")


if __name__ == "__main__":
    main()
