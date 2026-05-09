#!/usr/bin/env python3
"""
Hermes Portable - Windows 原生构建脚本
在 Windows 上运行此脚本，生成完全原生的 HermesPortable/ 文件夹。

用法:
  python build_windows.py                    # 构建到 dist/HermesPortable/
  python build_windows.py D:\\HermesPortable   # 构建到指定路径
"""
import os
import sys
import subprocess
import platform
import shutil
import zipfile
import io
from pathlib import Path
from datetime import datetime

# ─── Config ────────────────────────────────────────────────────
HERMES_REPO = "https://github.com/NousResearch/hermes-agent.git"
PYTHON_VERSION = "3.12"
PYTHON_BUILD = "3.12.9"
EXTRAS = "cron,messaging,cli,mcp,web"

# ─── ANSI Colors ───────────────────────────────────────────────
G = "\033[92m"
R = "\033[91m"
Y = "\033[93m"
C = "\033[96m"
B = "\033[1m"
X = "\033[0m"

def log(tag, color, msg):
    print(f"{color}[{tag}]{X} {msg}")

def info(m):   log("·", C, m)
def ok(m):     log("✓", G, m)
def warn(m):   log("!", Y, m)
def fail(m):   log("✗", R, m); sys.exit(1)

def banner():
    print(f"""
{B}{C}
  ╦ ╦╔═╗╦═╗╔═╗╔═╗╔═╗╔╦╗╔═╗
  ╠═╣╠═╣╠╦╝╠═╝║╣ ║   ║ ║ ║
  ╩ ╩╩ ╩╩╚═╩  ╚═╝╚═╝╩ ╩╚═╝{X}

  {B}Windows Native Builder{X}
  Python: {C}{PYTHON_BUILD}{X}
""")

def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)

def download(url, dest):
    info(f"Downloading {url.split('/')[-1]} ...")
    run(["curl", "-fSL", "-o", str(dest), url])

# ═══════════════════════════════════════════════════════════════
#  BUILD STEPS
# ═══════════════════════════════════════════════════════════════

def step_uv(ROOT):
    """Download uv for Windows."""
    uv_bin = ROOT / "uv.exe"
    if uv_bin.exists():
        ok("uv already present"); return

    # Check system uv
    system_uv = shutil.which("uv")
    if system_uv:
        info(f"Copying uv from {system_uv} ...")
        shutil.copy2(system_uv, uv_bin)
        ok("uv ready (from system)")
        return

    import struct
    arch = "x86_64" if struct.calcsize("P") * 8 == 64 else "i686"
    url = f"https://github.com/astral-sh/uv/releases/latest/download/uv-{arch}-pc-windows-msvc.zip"

    archive = ROOT / "_uv_tmp.zip"
    download(url, archive)

    with zipfile.ZipFile(archive) as z:
        for n in z.namelist():
            if n.endswith("uv.exe"):
                uv_bin.write_bytes(z.read(n))
                break
    archive.unlink(missing_ok=True)
    ok("uv ready")


def step_python(ROOT):
    """Install standalone Windows Python via uv."""
    py_dir = ROOT / "python"
    uv = ROOT / "uv.exe"

    if any(py_dir.rglob("python.exe")):
        ok("Python already present"); return

    info(f"Installing Python {PYTHON_VERSION} ...")
    env = os.environ.copy()
    env["UV_PYTHON_INSTALL_DIR"] = str(py_dir)
    try:
        run([str(uv), "python", "install", PYTHON_VERSION, "--install-dir", str(py_dir)], env=env)
        ok(f"Python {PYTHON_VERSION} installed")
    except subprocess.CalledProcessError:
        warn("uv python install failed, downloading embeddable Python directly")
        _download_embedded_python(ROOT)


def _download_embedded_python(ROOT):
    """Fallback: download Python embeddable zip directly."""
    py_dir = ROOT / "python"
    py_dir.mkdir(parents=True, exist_ok=True)

    url = f"https://www.python.org/ftp/python/{PYTHON_BUILD}/python-{PYTHON_BUILD}-embed-amd64.zip"
    archive = py_dir / "_py_embed.zip"
    download(url, archive)

    with zipfile.ZipFile(archive) as z:
        # Security: filter path traversal
        safe = [n for n in z.namelist() if not n.startswith('/') and '..' not in n]
        for n in safe:
            z.extract(n, py_dir)
    archive.unlink(missing_ok=True)

    # Enable import site (needed for pip)
    pth_file = py_dir / f"python{PYTHON_VERSION.replace('.', '')}._pth"
    if pth_file.exists():
        content = pth_file.read_text()
        if "import site" not in content:
            content = content.rstrip() + "\nimport site\n"
            pth_file.write_text(content)

    ok(f"Python {PYTHON_VERSION} (embeddable) installed")


def _find_python(ROOT):
    """Find python.exe in the portable python directory."""
    py_dir = ROOT / "python"
    # Direct search
    for f in py_dir.rglob("python.exe"):
        if f.is_file():
            return f
    fail("Cannot find python.exe after install")


def step_uv_bootstrap(ROOT):
    """Bootstrap pip into the embedded Python using get-pip.py."""
    py = _find_python(ROOT)
    pip_check = subprocess.run([str(py), "-m", "pip", "--version"],
                                capture_output=True)
    if pip_check.returncode == 0:
        ok("pip already available"); return

    info("Bootstrapping pip ...")
    get_pip = ROOT / "_get_pip.py"
    download("https://bootstrap.pypa.io/get-pip.py", get_pip)
    run([str(py), str(get_pip), "--no-warn-script-location"])
    get_pip.unlink(missing_ok=True)
    ok("pip ready")


def step_hermes(ROOT):
    """Clone hermes-agent."""
    src = ROOT / "hermes-agent"
    if src.exists() and (src / "run_agent.py").exists():
        ok("hermes-agent present"); return

    # Try local copy first
    local_src = Path.home() / ".hermes" / "hermes-agent"
    if local_src.exists() and (local_src / "run_agent.py").exists():
        info("Copying hermes-agent from local ...")
        shutil.copytree(local_src, src, ignore=shutil.ignore_patterns(
            "__pycache__", ".git", "node_modules", "venv", "*.pyc",
            "tests", ".pytest_cache", "*.egg-info",
            "docs", "docker", "Dockerfile", "flake.*",
            "RELEASE_*.md", "datagen-config-examples",
            ".github", ".vscode", ".idea",
        ))
        ok("hermes-agent copied from local")
        return

    info("Cloning hermes-agent from GitHub ...")
    try:
        run(["git", "clone", "--depth", "1", HERMES_REPO, str(src)])
        ok("hermes-agent cloned")
    except subprocess.CalledProcessError:
        fail("Cannot clone hermes-agent. Check internet connection.")


def step_venv(ROOT):
    """Create Windows venv and install deps."""
    venv = ROOT / "venv"
    py = _find_python(ROOT)
    src = ROOT / "hermes-agent"

    # Create venv
    if not (venv / "Scripts" / "python.exe").exists():
        info("Creating virtual environment ...")
        run([str(py), "-m", "venv", str(venv)])
        ok("venv created")

    py_venv = venv / "Scripts" / "python.exe"
    pip_venv = venv / "Scripts" / "pip.exe"

    # Upgrade pip
    info("Upgrading pip ...")
    run([str(py_venv), "-m", "pip", "install", "--upgrade", "pip"])

    # Install hermes-agent
    info(f"Installing hermes-agent[{EXTRAS}] — may take a few minutes ...")
    try:
        run([str(pip_venv), "install", "-e", f"{src}[{EXTRAS}]"])
    except subprocess.CalledProcessError:
        warn("Full extras failed, falling back to core ...")
        run([str(pip_venv), "install", "-e", str(src)])
    ok("Dependencies installed")


def step_data(ROOT):
    """Create data/ with default config."""
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
            "#  去掉 # 号，填入你的 Key\n"
            "# ═══════════════════════════════════════════\n\n"
            "# OPENROUTER_API_KEY=your-key-here\n"
            "# ANTHROPIC_API_KEY=your-key-here\n"
            "# OPENAI_API_KEY=your-key-here\n"
            "# DEEPSEEK_API_KEY=your-key-here\n"
            "# GOOGLE_API_KEY=your-key-here\n"
        )

    cfg = data / "config.yaml"
    if not cfg.exists():
        cfg.write_text(
            "# Hermes Portable — Configuration\n"
            "model:\n"
            '  default: "openrouter/anthropic/claude-sonnet-4"\n'
            '  provider: "openrouter"\n\n'
            "terminal:\n"
            '  backend: "local"\n'
            "  timeout: 180\n\n"
            "shell:\n"
            '  default: "powershell"\n\n'
            "compression:\n"
            "  enabled: true\n"
            "  threshold: 0.50\n"
            "  target_ratio: 0.20\n\n"
            "display:\n"
            '  skin: "default"\n'
            "  tool_progress: true\n"
            "  show_cost: true\n\n"
            "memory:\n"
            "  memory_enabled: true\n"
            "  user_profile_enabled: true\n"
        )
    ok("data/ ready")


def step_launchers(ROOT):
    """Write Windows-native launcher scripts."""
    # Copy helper scripts
    for fname in ("config_server.py", "chat_viewer.py", "update.py", "HermesPortable使用说明.html", "构建教程.html"):
        src = Path(__file__).parent / fname
        if src.exists():
            shutil.copy2(src, ROOT / fname)

    # ── Native Windows bat (no WSL!) ──
    bat = ROOT / "Hermes.bat"
    bat.write_text(
        "@echo off\r\n"
        "setlocal enabledelayedexpansion\r\n"
        'set "HERE=%~dp0"\r\n'
        'set "HERMES_HOME=%HERE%data"\r\n'
        'set "PATH=%HERE%venv\\Scripts;%HERE%node;%HERE%python;%PATH%"\r\n'
        "\r\n"
        "echo.\r\n"
        "echo   ╦ ╦╔═╗╦═╗╔═╗╔═╗╔═╗╔╦╗╔═╗\r\n"
        "echo   ╠═╣╠═╣╠╦╝╠═╝║╣ ║   ║ ║ ║\r\n"
        "echo   ╩ ╩╩ ╩╩╚═╩  ╚═╝╚═╝╩ ╩╚═╝  Portable\r\n"
        "echo.\r\n"
        "\r\n"
        "REM Check if native venv exists\r\n"
        'if not exist "%HERE%venv\\Scripts\\hermes.exe" (\r\n'
        "    echo   [ERROR] 未找到 venv\\Scripts\\hermes.exe\r\n"
        "    echo.\r\n"
        "    echo   请先运行构建脚本生成完整环境\r\n"
        "    echo.\r\n"
        "    pause\r\n"
        "    exit /b 1\r\n"
        ")\r\n"
        "\r\n"
        "REM Check if API key is configured\r\n"
        'set "HAS_KEY=false"\r\n'
        'if exist "%HERE%data\\.env" (\r\n'
        '    findstr /R "^[A-Z_]*_API_KEY=." "%HERE%data\\.env" >nul 2>&1\r\n'
        "    if !errorlevel! equ 0 set \"HAS_KEY=true\"\r\n"
        ")\r\n"
        "\r\n"
        'if "%HAS_KEY%"=="false" (\r\n'
        "    echo   首次使用！正在打开配置面板...\r\n"
        "    echo   请在浏览器中完成 API Key 配置。\r\n"
        "    echo.\r\n"
        '    start "" "http://127.0.0.1:17520"\r\n'
        '    "%HERE%venv\\Scripts\\python.exe" "%HERE%config_server.py"\r\n'
        "    goto :eof\r\n"
        ")\r\n"
        "\r\n"
        'if "%1"=="--config" (\r\n'
        '    start "" "http://127.0.0.1:17520"\r\n'
        '    "%HERE%venv\\Scripts\\python.exe" "%HERE%config_server.py"\r\n'
        "    goto :eof\r\n"
        ")\r\n"
        "\r\n"
        "REM Start hermes-web-ui in background (if installed)\r\n"
        'set "WEBUI_OK=false"\r\n'
        "where hermes-web-ui >nul 2>&1\r\n"
        "if !errorlevel! equ 0 (\r\n"
        "    start /b hermes-web-ui start --port 8648 >nul 2>&1\r\n"
        '    set "WEBUI_OK=true"\r\n'
        ")\r\n"
        "\r\n"
        '"%HERE%venv\\Scripts\\hermes.exe" %*\r\n'
    )

    # ── Config-only launcher ──
    bat_config = ROOT / "Hermes-Config.bat"
    bat_config.write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        'set "HERE=%~dp0"\r\n'
        'set "HERMES_HOME=%HERE%data"\r\n'
        'set "PATH=%HERE%venv\\Scripts;%HERE%node;%HERE%python;%PATH%"\r\n'
        'start "" "http://127.0.0.1:17520"\r\n'
        '"%HERE%venv\\Scripts\\python.exe" "%HERE%config_server.py"\r\n'
    )

    ok("Windows launchers written")


def step_cleanup(ROOT):
    """Remove build artifacts."""
    info("Cleaning build artifacts ...")
    removed = 0
    for d in ROOT.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True); removed += 1
    for f in ROOT.rglob("*.pyc"):
        f.unlink(missing_ok=True); removed += 1
    for f in ROOT.rglob(".DS_Store"):
        f.unlink(missing_ok=True); removed += 1
    for d in ROOT.rglob("*.egg-info"):
        shutil.rmtree(d, ignore_errors=True); removed += 1
    ok(f"Cleaned {removed} artifacts")


def step_readme(ROOT):
    (ROOT / "README.txt").write_text(
        "╔══════════════════════════════════════════╗\n"
        "║         HERMES  PORTABLE  v0.11.0           ║\n"
        "║       插上U盘，打开即用的 AI Agent       ║\n"
        "╚══════════════════════════════════════════╝\n"
        "\n"
        "【Windows 使用方法】\n"
        "  双击 Hermes.bat 即可启动（原生运行，无需 WSL2）\n"
        "  首次使用会自动打开配置面板\n"
        "\n"
        "【WSL2 备选】\n"
        "  如果原生运行遇到问题，可双击 Hermes-WSL.bat 通过 WSL2 运行\n"
        "\n"
        "【配置面板】\n"
        "  地址: http://127.0.0.1:17520\n"
        "  也可以双击 Hermes-Config.bat 打开\n"
        "\n"
        "【目录说明】\n"
        "  data\\             用户数据（配置/会话/技能）\n"
        "  data\\.env         API 密钥 ← 唯一需要编辑的文件\n"
        "  data\\config.yaml  配置文件\n"
        "  venv\\             Python 依赖\n"
        "  python\\           Python 运行时\n"
        "  hermes-agent\\\\     Hermes 源码\n"
        "\n"
        "【使用说明】\n"
        "  双击 HermesPortable使用说明.html 查看详细使用方法\n"
        "\n"
        "【已知限制】\n"
        "  - Windows 原生支持为 Early Beta\n"
        "  - 文件监听使用轮询（效率较低）\n"
        "  - 建议使用 Windows Terminal 获得最佳体验\n"
        "\n"
        "【更新】\n"
        "  双击 Hermes-Config.bat，在设置页点击「检查更新」\n"
        "\n"
        f"  构建时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    )
    ok("README.txt written")


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    banner()

    if platform.system() != "Windows":
        warn("此脚本用于 Windows 平台。macOS/Linux 请使用 build.py")
        if input("继续? (y/N): ").lower() != "y":
            sys.exit(0)

    # Determine output directory
    if len(sys.argv) > 1:
        ROOT = Path(sys.argv[1])
    else:
        ROOT = Path(__file__).parent / "dist" / "HermesPortable"

    ROOT.mkdir(parents=True, exist_ok=True)
    info(f"Output: {ROOT.resolve()}")

    steps = [
        ("Download uv",           step_uv),
        ("Install Python",        step_python),
        ("Bootstrap pip",         step_uv_bootstrap),
        ("Clone hermes-agent",    step_hermes),
        ("Create venv + deps",    step_venv),
        ("Setup data/",           step_data),
        ("Write launchers",       step_launchers),
        ("Cleanup",               step_cleanup),
        ("Write README",          step_readme),
    ]

    for name, fn in steps:
        info(f"Step: {name}")
        fn(ROOT)

    size = sum(f.stat().st_size for f in ROOT.rglob("*") if f.is_file()) / 1e6
    print(f"\n{G}{B}  ✓ Build complete!{X}")
    print(f"  Location: {C}{ROOT.resolve()}{X}")
    print(f"  Size: {C}{size:.0f} MB{X}")
    print(f"\n  双击 {B}Hermes.bat{X} 即可启动\n")


if __name__ == "__main__":
    main()
