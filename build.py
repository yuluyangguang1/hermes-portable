#!/usr/bin/env python3
"""
Hermes Portable - 构建脚本
运行此脚本会生成一个完全自包含的 HermesPortable/ 文件夹，
直接复制到U盘即可使用，无需任何安装步骤。

用法:
  python3 build.py          # 构建到当前目录下的 dist/
  python3 build.py /Volumes/U盘  # 构建到指定路径
"""
import os
import sys
import subprocess
import platform
import shutil
import zipfile
import tarfile
from pathlib import Path
from datetime import datetime

# ─── Config ────────────────────────────────────────────────────
HERMES_REPO = "https://github.com/NousResearch/hermes-agent.git"
PYTHON_VERSION = "3.12"
EXTRAS = "cron,messaging,cli,mcp,web,tts-premium"

# ─── ANSI Colors ───────────────────────────────────────────────
G = "\033[92m"  # green
R = "\033[91m"  # red
Y = "\033[93m"  # yellow
C = "\033[96m"  # cyan
B = "\033[1m"   # bold
X = "\033[0m"   # reset

def log(tag, color, msg):
    print(f"{color}[{tag}]{X} {msg}")

def info(m):   log("·", C, m)
def ok(m):     log("✓", G, m)
def warn(m):   log("!", Y, m)
def fail(m):   log("✗", R, m); sys.exit(1)

def banner():
    system = f"{platform.system()} {platform.machine()}"
    print(f"""
{B}{C}
  ╦ ╦╔═╗╦═╗╔═╗╔═╗╔═╗╔╦╗╔═╗
  ╠═╣╠═╣╠╦╝╠═╝║╣ ║   ║ ║ ║
  ╩ ╩╩ ╩╩╚═╩  ╚═╝╚═╝╩ ╩╚═╝{X}

  {B}Portable Builder{X}
  Target: {C}{system}{X}
  Python: {C}{PYTHON_VERSION}{X}
""")

def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)

def download(url, dest):
    """Download file using curl (available on all macOS/Linux)."""
    run(["curl", "-fSL", "-o", str(dest), url])

def detect_platform():
    s = platform.system()
    a = platform.machine().lower()
    arch = "x86_64" if a in ("x86_64", "amd64") else "aarch64"
    return s, arch

# ═══════════════════════════════════════════════════════════════
#  BUILD STEPS
# ═══════════════════════════════════════════════════════════════

def step_uv(ROOT):
    """Copy or link uv into the portable folder."""
    uv_bin = ROOT / ("uv.exe" if platform.system() == "Windows" else "uv")
    if uv_bin.exists():
        ok("uv already present"); return

    # Check system uv first
    system_uv = shutil.which("uv")
    if system_uv:
        info(f"Copying uv from {system_uv} …")
        shutil.copy2(system_uv, uv_bin)
        if platform.system() != "Windows":
            uv_bin.chmod(0o755)
        ok("uv ready (from system)")
        return

    system, arch = detect_platform()
    if system == "Darwin":
        url = f"https://github.com/astral-sh/uv/releases/latest/download/uv-{arch}-apple-darwin.tar.gz"
    elif system == "Linux":
        url = f"https://github.com/astral-sh/uv/releases/latest/download/uv-{arch}-unknown-linux-gnu.tar.gz"
    else:
        url = f"https://github.com/astral-sh/uv/releases/latest/download/uv-{arch}-pc-windows-msvc.zip"

    archive = ROOT / "_uv_tmp"
    info("Downloading uv …")
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
                if m.name.endswith("/uv"):
                    f = t.extractfile(m)
                    uv_bin.write_bytes(f.read())
                    break
    archive.unlink(missing_ok=True)
    if system != "Windows":
        uv_bin.chmod(0o755)
    ok("uv ready")


def step_python(ROOT):
    """Install a standalone Python into python/ via uv."""
    py_dir = ROOT / "python"
    uv = ROOT / ("uv.exe" if platform.system() == "Windows" else "uv")
    if any(py_dir.rglob("python3*")):
        ok("Python already present"); return

    info(f"Installing Python {PYTHON_VERSION} …")
    env = os.environ.copy()
    env["UV_PYTHON_INSTALL_DIR"] = str(py_dir)
    try:
        run([str(uv), "python", "install", PYTHON_VERSION, "--install-dir", str(py_dir)], env=env)
        ok(f"Python {PYTHON_VERSION} installed")
    except subprocess.CalledProcessError:
        warn("uv python install failed, using system Python as fallback")
        py_dir.mkdir(parents=True, exist_ok=True)
        # Create a symlink to system python
        sys_python = sys.executable
        target = py_dir / ("python3.12" if platform.system() != "Windows" else "python3.12.exe")
        if not target.exists():
            target.symlink_to(sys_python)
        ok(f"Using system Python: {sys_python}")


def _find_python(ROOT):
    py_dir = ROOT / "python"
    # Check symlinks first
    for f in py_dir.iterdir():
        if f.is_symlink() or f.is_file():
            if f.name in ("python3.12", "python3", "python",
                          "python3.12.exe", "python3.exe", "python.exe"):
                return f.resolve() if f.is_symlink() else f
    # Deep search
    for root, _, files in os.walk(py_dir):
        for f in files:
            if f in ("python3.12", "python3", "python",
                     "python3.12.exe", "python3.exe", "python.exe"):
                p = Path(root) / f
                if p.is_file(): return p
    fail("Cannot find python binary after install")


def step_hermes(ROOT):
    """Clone hermes-agent into hermes-agent/."""
    src = ROOT / "hermes-agent"
    if src.exists() and (src / "run_agent.py").exists():
        ok("hermes-agent present"); return

    # Try local copy first (faster, no network needed)
    local_src = Path.home() / ".hermes" / "hermes-agent"
    if local_src.exists() and (local_src / "run_agent.py").exists():
        info("Copying hermes-agent from local installation …")
        shutil.copytree(local_src, src, ignore=shutil.ignore_patterns(
            "__pycache__", ".git", "node_modules", "venv", "*.pyc",
            "tests", ".pytest_cache", "*.egg-info"
        ))
        ok("hermes-agent copied from local")
        return

    info("Cloning hermes-agent from GitHub …")
    try:
        run(["git", "clone", "--depth", "1", HERMES_REPO, str(src)])
        ok("hermes-agent cloned")
    except subprocess.CalledProcessError:
        fail("Cannot clone hermes-agent. Check your internet connection, "
             "or ensure ~/.hermes/hermes-agent exists.")


def step_venv(ROOT):
    """Create venv and install deps (offline-ready after this)."""
    venv = ROOT / "venv"
    uv  = ROOT / ("uv.exe" if platform.system() == "Windows" else "uv")
    src = ROOT / "hermes-agent"
    py  = _find_python(ROOT)

    # Create venv
    if not venv.exists():
        info("Creating virtual environment …")
        run([str(uv), "venv", str(venv), "--python", str(py)])
        ok("venv created")

    # Python inside venv
    if platform.system() == "Windows":
        py_venv = venv / "Scripts" / "python.exe"
    else:
        py_venv = venv / "bin" / "python"

    info(f"Installing hermes-agent[{EXTRAS}] — may take a few minutes …")
    try:
        run([str(uv), "pip", "install", "-e", f"{src}[{EXTRAS}]",
             "--python", str(py_venv)])
    except subprocess.CalledProcessError:
        warn("Full extras failed, falling back to core …")
        run([str(uv), "pip", "install", "-e", str(src),
             "--python", str(py_venv)])
    ok("Dependencies installed")


def step_data(ROOT):
    """Create data/ with default config if missing."""
    data = ROOT / "data"
    dirs = ["sessions", "skills", "logs", "memories", "cron",
            "plugins", "audio_cache", "image_cache", "checkpoints"]
    for d in dirs:
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
            "# GOOGLE_API_KEY=...\n"
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
            "  user_profile_enabled: true\n"
        )
    ok("data/ ready")


def step_launchers(ROOT):
    """Write launcher scripts that set HERMES_HOME and go."""
    # ── Windows ──
    (ROOT / "Hermes.bat").write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        "set \"HERE=%~dp0\"\r\n"
        "set \"HERMES_HOME=%HERE%data\"\r\n"
        "set \"PATH=%HERE%venv\\Scripts;%HERE%python;%PATH%\"\r\n"
        "cd /d \"%HERE%\"\r\n"
        "\"%HERE%venv\\Scripts\\hermes.exe\" %*\r\n"
        "if %errorlevel% neq 0 pause\r\n"
    )
    # ── Unix ──
    sh = ROOT / "Hermes.command"       # .command double-clickable on macOS
    sh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'HERE="$(cd "$(dirname "$0")" && pwd)"\n'
        'export HERMES_HOME="$HERE/data"\n'
        'export PATH="$HERE/venv/bin:$HERE/python:$PATH"\n'
        'cd "$HERE"\n'
        'exec "$HERE/venv/bin/hermes" "$@"\n'
    )
    sh.chmod(0o755)

    # Also a plain .sh for Linux terminals
    sh2 = ROOT / "Hermes.sh"
    sh2.write_text(sh.read_text())
    sh2.chmod(0o755)

    ok("Launchers written")


def step_readme(ROOT):
    (ROOT / "README.txt").write_text(
        "╔══════════════════════════════════════════╗\n"
        "║         HERMES  PORTABLE  v0.9           ║\n"
        "║       插上U盘，打开即用的 AI Agent       ║\n"
        "╚══════════════════════════════════════════╝\n"
        "\n"
        "【首次使用】\n"
        "  1. 打开 data/.env 文件\n"
        "  2. 填入你的 API Key（去掉前面的 #）\n"
        "  3. 双击启动：\n"
        "     Windows  →  Hermes.bat\n"
        "     macOS    →  Hermes.command  (双击即可)\n"
        "     Linux    →  终端运行 ./Hermes.sh\n"
        "\n"
        "【目录说明】\n"
        "  data/           所有用户数据（配置/会话/技能）\n"
        "  data/.env       API 密钥\n"
        "  data/config.yaml  配置文件\n"
        "  venv/           Python 依赖（勿动）\n"
        "  python/         Python 运行时（勿动）\n"
        "  hermes-agent/   Hermes 源码（勿动）\n"
        "\n"
        "【更新 Hermes】\n"
        "  cd hermes-agent && git pull && cd ..\n"
        "  venv/bin/pip install -e hermes-agent[all]\n"
        "\n"
        "【备份】\n"
        "  只需备份 data/ 目录即可。\n"
    )
    ok("README.txt written")


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    banner()

    # Determine output directory
    if len(sys.argv) > 1:
        ROOT = Path(sys.argv[1]).resolve() / "HermesPortable"
    else:
        ROOT = Path(__file__).parent / "dist" / "HermesPortable"

    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "data").mkdir(exist_ok=True)

    info(f"Build target: {ROOT}")
    print()

    steps = [
        ("Downloading uv (package manager)",      step_uv),
        ("Installing portable Python",             step_python),
        ("Cloning hermes-agent",                   step_hermes),
        ("Creating venv & installing deps",        step_venv),
        ("Setting up data directory",              step_data),
        ("Writing launcher scripts",               step_launchers),
        ("Writing README",                         step_readme),
    ]

    for i, (desc, fn) in enumerate(steps, 1):
        print(f"{B}[{i}/{len(steps)}] {desc}{X}")
        fn(ROOT)
        print()

    # Summary
    total_size = sum(f.stat().st_size for f in ROOT.rglob("*") if f.is_file())
    total_mb = total_size / (1024 * 1024)

    print(f"""
{G}{B}
  ╔═══════════════════════════════════════╗
  ║        BUILD COMPLETE  ✓             ║
  ╚═══════════════════════════════════════╝
{X}
  Output : {C}{ROOT}{X}
  Size   : {C}{total_mb:.0f} MB{X}

  {B}下一步:{X}
  1. 把 {C}HermesPortable/{X} 整个文件夹复制到U盘
  2. 编辑 {C}data/.env{X} 填入 API Key
  3. 双击启动：
     • macOS   → Hermes.command
     • Windows → Hermes.bat
     • Linux   → ./Hermes.sh

  🚀 零安装，即插即用！
""")


if __name__ == "__main__":
    main()
