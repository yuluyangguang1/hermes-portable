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
HERMES_TAG = None  # None = latest release, or set to specific tag like "v2026.7.1"
PYTHON_VERSION = "3.12"
EXTRAS = "cron,messaging,cli,mcp,web,tts-premium"
# Node 24 LTS (active LTS until 2026-10, maintenance until 2028-04).
# Pinned to Node 22 LTS: Node 24.15.0 crashes on Windows with
# "Assertion failed: ncrypto::CSPRNG(nullptr, 0)" during npm install, and
# Node 24's npm also needs a working `sh` on the PATH (see step_nodejs).
# Node 22 LTS is stable across macOS/Linux/Windows and its npm tarball
# ships the same bin/npm -> ../lib/node_modules/npm/bin/npm-cli.js symlink.
# Per-platform Node.js versions.
# macOS/Linux ship Node 24 LTS (matches "24+" expectation, supports the
# hermes-web-ui runtime). Windows CI runners hit a ncrypto::CSPRNG crash on
# Node 24.15.0 (exit 134, "Assertion failed: ncrypto::CSPRNG(nullptr, 0)"),
# so Windows stays on 22 LTS until that build is fixed.
NODE_VERSION = "24.15.0"          # default (macOS/Linux)
NODE_VERSION_WINDOWS = "22.15.0"  # Windows CI workaround

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


def download_with_checksum(url, dest, expected_sha256):
    """Download a file and verify its SHA-256 checksum.

    Falls back to plain download if the checksum doesn't match,
    printing a warning. This is defense-in-depth: a corrupted download
    from a throttled mirror would otherwise cause confusing errors
    later (e.g. tar extraction failure, missing binaries).
    """
    import hashlib
    download(url, dest)
    if expected_sha256:
        actual = hashlib.sha256(dest.read_bytes()).hexdigest()
        if actual != expected_sha256:
            warn(f"Checksum mismatch for {dest.name}: expected {expected_sha256[:16]}…, got {actual[:16]}…")
            # Don't fail — the file might still be usable. But warn loudly.
        else:
            ok(f"Checksum verified: {dest.name}")

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
            "    (symlinks + hardcoded paths in pyvenv.cfg break).\n"
        )

    # Fix execute permissions on Python binaries.
    # uv python install may not preserve execute bits in some environments,
    # causing "Permission denied" when the launcher tries to run python3.
    # This is especially common on macOS where zip extraction can lose
    # execute permissions.
    if system != "Windows":
        for bin_dir in py_dir.rglob("bin"):
            if bin_dir.is_dir():
                for f in bin_dir.iterdir():
                    if f.name.startswith("python") and f.is_file():
                        f.chmod(0o755)

    # Clear macOS quarantine attributes (com.apple.quarantine).
    # python-build-standalone binaries are unsigned, and macOS Gatekeeper
    # will block them with "Unable to verify developer" errors.
    # We strip the xattr so the binaries run without user intervention.
    if system == "Darwin":
        info("Clearing macOS quarantine attributes …")
        try:
            subprocess.run(["xattr", "-rc", str(ROOT)], check=False)
            ok("Quarantine attributes cleared")
        except FileNotFoundError:
            warn("xattr not found — skipping quarantine cleanup (non-macOS build?)")


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
        if HERMES_TAG:
            run(["git", "clone", "--depth", "1", "--branch", HERMES_TAG, HERMES_REPO, str(src)])
        else:
            run(["git", "clone", "--depth", "1", HERMES_REPO, str(src)])
        _clean_hermes_src(src)
        ok("hermes-agent cloned")
    except subprocess.CalledProcessError:
        fail("Cannot clone hermes-agent. Check internet connection, "
             "or ensure ~/.hermes/hermes-agent exists.")


def _fix_editable_paths(venv, system, src):
    """Rewrite absolute paths in editable finder files to be relocatable.

    uv creates __editable___<package>_<version>_finder.py with absolute
    paths in BOTH the MAPPING dict and the NAMESPACES dict. We rewrite them
    to resolve relative to the finder file's own location (via __file__),
    so the portable bundle works no matter where it is extracted
    (USB key, /Volumes, any user path).

    Previously only MAPPING was fixed and the relative path was resolved
    against CWD, which broke on user machines with
    "ModuleNotFoundError: No module named 'hermes_cli'".
    """
    if system == "Windows":
        site_packages = venv / "Lib" / "site-packages"
    else:
        site_packages = venv / "lib" / f"python{ctx_python_version(venv)}" / "site-packages"

    if not site_packages.exists():
        warn(f"Site-packages not found at {site_packages}")
        return

    finder_files = sorted(site_packages.glob("__editable__*_finder.py"))
    if not finder_files:
        return

    src_abs = str(src.resolve()).rstrip("/")
    prefix = src_abs + "/"

    # Base dir: the portable bundle root that contains both `venv/` and
    # `hermes-agent/`. Walk UP from this finder file until we find the dir
    # that actually contains `hermes-agent/` (site-packages depth varies
    # between the CI build tree `dist/HermesPortable/...` and a user's
    # arbitrary extract path, so we search instead of hard-coding a level
    # count — a fixed count of 4 was off by one and resolved to `venv/`,
    # breaking `import hermes_cli` on user machines).
    inject = (
        "import os as _os\n"
        "_CUR = _os.path.dirname(_os.path.abspath(__file__))\n"
        "while _CUR and _CUR != _os.path.dirname(_CUR):\n"
        "    if _os.path.isdir(_os.path.join(_CUR, 'hermes-agent')):\n"
        "        break\n"
        "    _CUR = _os.path.dirname(_CUR)\n"
        "_BASE = _CUR\n"
        '_HERMES_AGENT = _os.path.join(_BASE, "hermes-agent")\n\n'
    )
    old = "'" + prefix
    new = "_HERMES_AGENT + '/"

    for finder_file in finder_files:
        content = finder_file.read_text(encoding="utf-8")
        if prefix not in content:
            continue
        if "MAPPING:" in content:
            content = content.replace("MAPPING:", inject + "MAPPING:", 1)
        else:
            content = inject + content
        new_content = content.replace(old, new)
        new_content = new_content.replace(inject + inject, inject)
        finder_file.write_text(new_content, encoding="utf-8")
        ok(f"Fixed editable paths in {finder_file.name}")


def _fix_hermes_shim(venv, system):
    """Make the uv-generated hermes launcher relocatable on macOS.

    uv's relocatable venv writes a shim whose exec line points at
    `$VENV/python` (one level above bin/), e.g.:
        '''exec' "$(dirname -- "$(dirname -- "$0")")"/'python' "$0" "$@"
    but the actual interpreter lives at `$VENV/bin/python` (uv also drops a
    real 18MB binary there that redirects via pyvenv.cfg's `home`). On a
    stock macOS, `$VENV/python` does not exist, so hermes dies with
    "No such file or directory". Rewrite the exec line to use the bin/ copy.
    """
    if system == "Windows":
        shim = venv / "Scripts" / "hermes.exe"
    else:
        shim = venv / "bin" / "hermes"
    if not shim.exists():
        return
    content = shim.read_text(encoding="utf-8", errors="replace")
    orig = content
    # Case 1: realpath-based (older uv)
    if "realpath -- " in content:
        content = content.replace("realpath -- ", "dirname -- ", 1)
    # Case 2: dirname(dirname($0))/python — points one level too high.
    # Rewrite to dirname($0)/python (i.e. $VENV/bin/python, which exists).
    if "$(dirname -- \"$(dirname -- \"$0\")\")" in content:
        content = content.replace(
            "$(dirname -- \"$(dirname -- \"$0\")\")",
            "$(dirname -- \"$0\")",
        )
    if content != orig:
        shim.write_text(content, encoding="utf-8")
        ok(f"Fixed hermes launcher shim in {shim}")


def ctx_python_version(venv):
    """Detect Python version from venv directory structure."""
    if (venv / "lib").exists():
        for d in sorted((venv / "lib").iterdir()):
            if d.name.startswith("python"):
                return d.name[len("python"):]
    return "3.12"


def step_venv(ctx):
    """Create venv via `uv venv` (relocatable) and install deps via editable install.

    NOTE: hermes-agent's setup.py now blocks non-editable (wheel/sdist) installs
    with a RuntimeError. Editable installs must be used instead, but they write
    absolute paths into site-packages/__editable__.*.py finder files. We
    post-process those files to convert absolute paths to relative paths so
    the portable bundle remains relocatable (USB key drive letter changes,
    /Volumes/USB name changes, etc.).
    """
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

    info(f"Installing hermes-agent[{EXTRAS}] (editable) …")
    # Use editable install (-e) since hermes-agent blocks wheel/sdist builds.
    # The setup.py guard only fires for bdist_wheel/sdist, not build_editable.
    try:
        run([str(uv), "pip", "install", "-e", f"{src}[{EXTRAS}]",
             "--python", str(py_venv)])
    except subprocess.CalledProcessError:
        warn("Full extras failed, falling back to core …")
        run([str(uv), "pip", "install", "-e", str(src),
             "--python", str(py_venv)])
    ok("Dependencies installed")

    # Post-process editable finder files to make paths relative.
    # uv creates __editable___<package>_<version>_finder.py files with
    # absolute paths in the MAPPING dict. We rewrite them to use
    # relative paths so the bundle is relocatable.
    _fix_editable_paths(venv, system, src)
    _fix_hermes_shim(venv, system)

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
    # Create _home/.hermes symlink (relative, not absolute)
    home_dir = ROOT / "_home"
    home_dir.mkdir(parents=True, exist_ok=True)
    hermes_link = home_dir / ".hermes"
    if hermes_link.exists() or hermes_link.is_symlink():
        hermes_link.unlink()
    hermes_link.symlink_to("../../data")
    ok("data/ ready")


def step_nodejs(ctx):
    ROOT, system, arch = ctx["ROOT"], ctx["system"], ctx["arch"]
    node_dir = ROOT / ctx["node_name"]
    src = ROOT / "hermes-agent"
    exe = "node.exe" if system == "Windows" else "node"
    if node_dir.exists() and any(node_dir.rglob(exe)):
        ok("Node.js already present"); return

    # Node.js uses x64 / arm64 (same as our label suffixes).
    node_arch = {"x64": "x64", "arm64": "arm64"}.get(arch, arch)
    if system == "Darwin":
        url = f"https://nodejs.org/dist/v{node_ver}/node-v{node_ver}-darwin-{node_arch}.tar.gz"
    elif system == "Linux":
        # Prebuilt Linux tarballs require glibc ≥ 2.28 (no change from
        # v22 → v24). On older hosts (RHEL 7, Debian 9, Ubuntu 18.04 and
        # earlier) the binary fails with GLIBC_2.xx-not-found — that's
        # a target-side issue we can't paper over here; document it in
        # README.txt instead.
        url = f"https://nodejs.org/dist/v{node_ver}/node-v{node_ver}-linux-{node_arch}.tar.gz"
    elif system == "Windows":
        # Node.js v24+ does ship Windows arm64 prebuilt, but the launcher
        # bat file currently only knows about x64; sticking with x64 keeps
        # behavior identical on ARM hardware (runs under Prism emulation,
        url = f"https://nodejs.org/dist/v{node_ver}/node-v{node_ver}-win-x64.zip"
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
        nested = node_dir / f"node-v{node_ver}-win-x64"
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
        nested = node_dir / f"node-v{node_ver}-{system.lower()}-{node_arch}"
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

    # NOTE: Do NOT hand-rewrite bin/npm / bin/npx here. The Node.js tarball
    # ships them as symlinks (bin/npm -> ../lib/node_modules/npm/bin/npm-cli.js)
    # which already work for portable installs. Path.write_text() follows
    # symlinks and would overwrite the link TARGET (npm-cli.js) with a broken
    # require("../lib/node_modules/npm/lib/cli.js") — breaking npm itself and
    # making `npm install` fail with MODULE_NOT_FOUND (the v1.20.x webui bug).

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

    # Actually run npm --version: exists() can't catch a symlink whose
    # target was clobbered by a bad write_text (the v1.20.x webui bug).
    # Fail the build loudly instead of shipping a broken npm.
    if system != "Windows":
        try:
            run([str(node_dir / "bin" / "node"),
                 str(node_dir / "bin" / "npm"), "--version"])
        except subprocess.CalledProcessError as e:
            fail(f"npm is present but broken (cannot run --version): {e}")

    ok(f"Node.js v{node_ver} ready ({system})")

    # Install hermes-web-ui globally (includes both server and client)
    # Using @latest + --force to ensure the newest version is always installed
    # Note: We don't use --omit=optional as it skips important UI components
    if system == "Windows":
        npm = node_dir / "npm.cmd"
    else:
        npm = node_dir / "bin" / "npm"
    if npm.exists():
        info("Installing hermes-web-ui (latest from npm) …")
        try:
            path_sep = ";" if system == "Windows" else ":"
            # Prepend node/bin BUT inherit the real system PATH so that npm
            # lifecycle scripts (e.g. node-pty's postinstall `spawn sh`) can
            # find /bin/sh, make, cc, etc. Using only node/bin here made npm
            # fail with ENOENT "spawn sh" and exit 254, silently shipping a
            # package without hermes-web-ui.
            env = {**ctx.get("env", {}),
                   "PATH": str(node_dir / "bin") + path_sep + os.environ.get("PATH", "")}
            # Install latest hermes-web-ui globally. We intentionally do NOT
            # run `npm cache clean --force` first: it is an optional optimisation
            # that segfaults (exit 134) on some CI Node builds and must not
            # block the install. `--force` on the install already pulls the
            # newest published version.
            #
            # Windows CI runners hit intermittent DNS failures (EAI_FAIL) when
            # reaching registry.npmjs.org, which makes a single `npm install`
            # fail even though github.com / nodejs.org downloads succeeded.
            # Mitigate with: (a) up to 3 retries, and (b) a China mirror
            # (npmmirror.com) as a fallback registry — both raise the odds of
            # a successful install on flaky runners.
            registries = ["https://registry.npmjs.org/",
                          "https://registry.npmmirror.com/"]
            installed = False
            last_err = None
            for attempt in range(1, 4):
                for reg in registries:
                    try:
                        run([str(npm), "install", "-g", "hermes-web-ui@latest",
                             "--force", "--registry", reg], env=env)
                        installed = True
                        ok(f"hermes-web-ui installed (attempt {attempt}, {reg})")
                        break
                    except Exception as e:
                        last_err = e
                        info(f"  npm install attempt {attempt} via {reg} failed: {e}")
                if installed:
                    break
                time.sleep(5 * attempt)
            if not installed:
                fail(f"hermes-web-ui install failed after retries: {last_err}")
        except Exception as e:
            # A broken web UI install means the package ships without a
            # working Web UI. Fail loudly — a silent warn let v1.20.x
            # ship zips where `npm install` had died on the bad shim.
            fail(f"hermes-web-ui install failed: {e}")
            fail(f"hermes-web-ui install failed: {e}")

    # ── Fix hermes-web-ui CLI path resolution for portable layout ──
    # The `hermes-web-ui` bin script (node/bin/hermes-web-ui) resolves its
    # server entry as  resolve(__dirname, "..", "dist", "server", "index.js"),
    # i.e. node/dist/server/index.js. But `npm install -g` puts the package at
    # node/lib/node_modules/hermes-web-ui/dist, so the CLI can't find its
    # server (MODULE_NOT_FOUND → Web UI silently never starts).
    # Also: the CLI bin is ESM (import …), so node/ needs a package.json with
    # "type":"module" or Node refuses to parse it as a module.
    webui_pkg = node_dir / "lib" / "node_modules" / "hermes-web-ui"
    dist_src = webui_pkg / "dist"
    # Create node/dist (copy, not symlink — zip may not preserve symlinks).
    dist_dst = node_dir / "dist"
    if dist_src.exists() and not dist_dst.exists():
        try:
            shutil.copytree(str(dist_src), str(dist_dst))
            ok("linked node/dist -> hermes-web-ui/dist (portable webui fix)")
        except Exception as e:
            warn(f"could not copy node/dist: {e}")
    # Write node/package.json with type:module so the ESM bin script parses.
    pkg_json = node_dir / "package.json"
    if not pkg_json.exists():
        try:
            pkg_json.write_text(
                '{"name":"hermes-web-ui-portable","version":"0.0.0","type":"module"}\n')
            ok("wrote node/package.json (type:module)")
        except Exception as e:
            warn(f"could not write node/package.json: {e}")
# Paths are relative to the repo root. Directory structure is preserved
# in the dist (e.g. "lib/config_server.py" → ROOT/lib/config_server.py).
_STATIC_ASSETS = [
    # lib/ — runtime internals (referenced by launchers)
    "lib/config_server.py",
    "lib/chat_viewer.py",
    "lib/update.py",
    "lib/update.sh",
    "lib/fix_shims.py",
    # lib/config/ — config server UI
    "lib/config/index.html",
    "lib/config/index-standalone.html",
    # Root — user-facing docs and assets
    "favicon.svg",
    "HermesPortable使用说明.html",
    # Launchers
    "Hermes.command",
    "Hermes.sh",
    "Hermes.bat",
    "Hermes-WSL.bat",
    # tools/ — rebuild helpers shipped so a user who carried a macOS-built
    # zip onto a Linux box can rebuild the runtime without re-downloading.
    "tools/build.py",
    "tools/linux-rebuild.sh",
    "tools/mac-rebuild.sh",
]


def step_launchers(ctx):
    ROOT = ctx["ROOT"]
    repo = Path(__file__).parent.parent  # tools/ -> repo root
    for fname in _STATIC_ASSETS:
        src = repo / fname
        if not src.exists():
            warn(f"missing in repo: {fname}")
            continue
        dst = ROOT / fname
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        # executable bits for unix launchers / scripts
        if fname.endswith((".sh", ".command")):
            try: dst.chmod(0o755)
            except Exception: pass
    ok("Launchers + lib/ + tools/ copied from repo")


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
    # Replace symlinks with copies for exFAT/Windows compatibility
    # EXCEPT _home/.hermes — that's a runtime symlink recreated by the
    # launchers on every start. Replacing it with a copy of data/ would
    # (a) duplicate the entire data/ directory, (b) make _home/.hermes
    # a real directory instead of a symlink, and (c) cause the launcher
    # to refuse to start (it expects a symlink, not a real dir).
    import shutil as _shutil
    symlink_count = 0
    for link in ROOT.rglob("*"):
        if link.is_symlink():
            # Skip the runtime sandbox symlink — launchers create it at runtime
            if link.name == ".hermes" and link.parent.name == "_home":
                continue
            target = link.resolve()
            # Only copy if the target is inside ROOT — prevents accidentally
            # bundling sensitive files (e.g. /etc/passwd) that a symlink
            # might point to.
            try:
                target.relative_to(ROOT)
            except ValueError:
                continue
            if target.exists():
                link.unlink()
                if target.is_dir():
                    _shutil.copytree(target, link)
                else:
                    _shutil.copy2(target, link)
                symlink_count += 1
    if symlink_count > 0:
        ok(f"Replaced {symlink_count} symlinks with copies")

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
    elif system == "Linux":
        _download_linux_desktop(url, runtime_dir)

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
        ROOT = Path(__file__).parent.parent / "dist" / "HermesPortable"
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
        except KeyboardInterrupt:
            fail(f"Build interrupted by user (step: {desc})")
        except Exception as e:
            import traceback; traceback.print_exc()
            fail(f"Step '{desc}' failed: {e}")
        print()

    total_bytes = sum(f.stat().st_size for f in ROOT.rglob("*") if f.is_file())

    # Final cleanup: clear macOS quarantine attributes on the entire build.
    # python-build-standalone binaries are unsigned, and macOS Gatekeeper
    # blocks them. This also ensures the zip archive doesn't carry
    # com.apple.quarantine xattrs that would affect end users.
    if system == "Darwin":
        info("Final cleanup: clearing macOS quarantine attributes …")
        try:
            subprocess.run(["xattr", "-rc", str(ROOT)], check=False)
            ok("Quarantine attributes cleared")
        except FileNotFoundError:
            warn("xattr not found — skipping quarantine cleanup")

    # Ensure all launcher / interpreter / node binaries are executable so the
    # shipped zip preserves +x after extraction. upload-artifact and some zip
    # round-trips drop the Unix exec bit, and relying on the CI chmod glob
    # alone left python3 without +x on macOS (Preflight "Python not found").
    info("Final step: ensuring binaries are executable …")
    made_exec = 0
    for bindir in (ROOT / "venv" / "bin", ROOT / "venv" / "Scripts",
                   ROOT / "python", ROOT / "node" / "bin"):
        if bindir.exists():
            for f in bindir.rglob("*"):
                if f.is_file():
                    try:
                        f.chmod(f.stat().st_mode | 0o111)
                        made_exec += 1
                    except OSError:
                        pass
    for pdir in ROOT.glob("python-*"):
        if pdir.is_dir():
            for f in pdir.rglob("*"):
                if f.is_file():
                    try:
                        f.chmod(f.stat().st_mode | 0o111)
                    except OSError:
                        pass
    ok(f"Ensured {made_exec}+ binaries executable (exec bit set)")
    print(f"{G}{B}  ✓ Build complete{X}")
    print(f"  Location: {C}{ROOT}{X}")
    print(f"  Size    : {C}{total_bytes / 1e6:.0f} MB{X}")
    if not args.no_desktop:
        print(f"  Desktop : {C}runtime/desktop/{X}")
    print(f"  Launchers: {C}Hermes.command / Hermes.sh / Hermes.bat{X}\n")


if __name__ == "__main__":
    main()
