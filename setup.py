#!/usr/bin/env python3
"""
Hermes Portable - 通用安装脚本
自动检测系统环境，下载所需依赖，完成便携式安装。
"""
import os
import sys
import subprocess
import platform
import shutil
import json
from pathlib import Path

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

SCRIPT_DIR = Path(__file__).parent.resolve()
PORTABLE_DIR = SCRIPT_DIR / "portable"
DATA_DIR = SCRIPT_DIR / "data"
UV_PATH = PORTABLE_DIR / ("uv.exe" if platform.system() == "Windows" else "uv")

def info(msg):
    print(f"{CYAN}[*]{RESET} {msg}")

def success(msg):
    print(f"{GREEN}[✓]{RESET} {msg}")

def warn(msg):
    print(f"{YELLOW}[!]{RESET} {msg}")

def error(msg):
    print(f"{RED}[✗]{RESET} {msg}")

def banner():
    print(f"""
{BOLD}{CYAN}
  ╦ ╦╔═╗╦═╗╔═╗╔═╗╔═╗╔╦╗╔═╗
  ╠═╣╠═╣╠╦╝╠═╝║╣ ║   ║ ║ ║
  ╩ ╩╩ ╩╩╚═╩  ╚═╝╚═╝╩ ╩╚═╝{RESET}
  
  {BOLD}Portable Setup Script{RESET}
  {CYAN}Platform: {platform.system()} {platform.machine()}{RESET}
""")

def run_cmd(cmd, check=True, capture=False):
    """Run a shell command."""
    kwargs = {}
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
        kwargs["text"] = True
    result = subprocess.run(cmd, check=check, **kwargs)
    return result

def download_file(url, dest):
    """Download a file using curl or urllib."""
    info(f"Downloading {url}...")
    try:
        import urllib.request
        urllib.request.urlretrieve(url, dest)
    except Exception:
        # Fallback to curl
        run_cmd(["curl", "-L", "-o", str(dest), url])

def setup_directories():
    """Create all necessary directories."""
    info("Creating directory structure...")
    dirs = [
        PORTABLE_DIR,
        DATA_DIR,
        DATA_DIR / "sessions",
        DATA_DIR / "skills",
        DATA_DIR / "logs",
        DATA_DIR / "memories",
        DATA_DIR / "cron",
        DATA_DIR / "plugins",
        DATA_DIR / "audio_cache",
        DATA_DIR / "image_cache",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    success("Directory structure created.")

def install_uv():
    """Download and install uv."""
    if UV_PATH.exists():
        success("uv already installed.")
        return

    info("Downloading uv package manager...")
    system = platform.system()
    arch = platform.machine().lower()

    if arch in ("x86_64", "amd64"):
        arch_suffix = "x86_64"
    elif arch in ("aarch64", "arm64"):
        arch_suffix = "aarch64"
    else:
        error(f"Unsupported architecture: {arch}")
        sys.exit(1)

    if system == "Windows":
        url = f"https://github.com/astral-sh/uv/releases/latest/download/uv-{arch_suffix}-pc-windows-msvc.zip"
    elif system == "Darwin":
        url = f"https://github.com/astral-sh/uv/releases/latest/download/uv-{arch_suffix}-apple-darwin.tar.gz"
    else:
        url = f"https://github.com/astral-sh/uv/releases/latest/download/uv-{arch_suffix}-unknown-linux-gnu.tar.gz"

    archive_path = PORTABLE_DIR / "uv_archive"
    download_file(url, archive_path)

    # Extract
    if system == "Windows":
        import zipfile
        with zipfile.ZipFile(archive_path, "r") as z:
            z.extractall(PORTABLE_DIR)
            # Find uv.exe
            for name in z.namelist():
                if name.endswith("uv.exe"):
                    shutil.move(PORTABLE_DIR / name, UV_PATH)
                    break
    else:
        import tarfile
        with tarfile.open(archive_path, "r:gz") as t:
            for member in t.getmembers():
                if member.name.endswith("/uv") or member.name == "uv":
                    # Extract just the uv binary
                    f = t.extractfile(member)
                    with open(UV_PATH, "wb") as out:
                        shutil.copyfileobj(f, out)
                    break

    # Cleanup
    archive_path.unlink(missing_ok=True)
    for d in PORTABLE_DIR.glob("uv-*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)

    if system != "Windows":
        UV_PATH.chmod(0o755)

    success("uv installed successfully.")

def install_python():
    """Install portable Python using uv."""
    python_dir = PORTABLE_DIR / "python"
    info("Installing portable Python 3.12...")

    env = os.environ.copy()
    env["UV_PYTHON_INSTALL_DIR"] = str(python_dir)

    subprocess.run(
        [str(UV_PATH), "python", "install", "3.12", "--install-dir", str(python_dir)],
        env=env, check=True
    )
    success("Python 3.12 installed.")

def find_python():
    """Find the installed Python binary."""
    python_dir = PORTABLE_DIR / "python"
    patterns = [
        "python3.12", "python3", "python",
        "python3.12.exe", "python3.exe", "python.exe",
    ]
    for root, dirs, files in os.walk(python_dir):
        for f in files:
            for pattern in patterns:
                if f == pattern:
                    candidate = Path(root) / f
                    if candidate.is_file():
                        return candidate
    return None

def clone_hermes():
    """Clone hermes-agent repository."""
    hermes_src = PORTABLE_DIR / "hermes-agent"
    if hermes_src.exists() and (hermes_src / "run_agent.py").exists():
        info("hermes-agent exists, pulling latest...")
        try:
            subprocess.run(
                ["git", "-C", str(hermes_src), "pull", "--ff-only"],
                check=False, capture_output=True
            )
            success("hermes-agent updated.")
        except Exception:
            warn("Could not update, using existing version.")
        return

    info("Cloning hermes-agent...")
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1",
             "https://github.com/NousResearch/hermes-agent.git",
             str(hermes_src)],
            check=True
        )
        success("hermes-agent cloned.")
    except subprocess.CalledProcessError:
        error("Failed to clone hermes-agent. Please install git:")
        error("  macOS:   brew install git")
        error("  Ubuntu:  sudo apt install git")
        error("  Windows: https://git-scm.com/download/win")
        sys.exit(1)

def create_venv(python_bin):
    """Create virtual environment."""
    venv_dir = PORTABLE_DIR / "venv"
    if venv_dir.exists():
        success("Virtual environment already exists.")
        return

    info("Creating virtual environment...")
    subprocess.run(
        [str(UV_PATH), "venv", str(venv_dir), "--python", str(python_bin)],
        check=True
    )
    success("Virtual environment created.")

def install_deps():
    """Install hermes-agent dependencies."""
    venv_dir = PORTABLE_DIR / "venv"
    hermes_src = PORTABLE_DIR / "hermes-agent"
    python_in_venv = venv_dir / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")

    info("Installing hermes-agent dependencies (this may take a few minutes)...")

    # Try full install first
    extras = ["all"]
    for extra in extras:
        try:
            subprocess.run(
                [str(UV_PATH), "pip", "install", "-e", f"{hermes_src}[{extra}]",
                 "--python", str(python_in_venv)],
                check=True
            )
            success(f"Installed with '{extra}' extras.")
            return
        except subprocess.CalledProcessError:
            warn(f"'{extra}' extras failed, trying lighter set...")

    # Fallback to core + common
    fallback_extras = "cron,messaging,cli,mcp"
    try:
        subprocess.run(
            [str(UV_PATH), "pip", "install", "-e", f"{hermes_src}[{fallback_extras}]",
             "--python", str(python_in_venv)],
            check=True
        )
        success(f"Installed with fallback extras: {fallback_extras}")
    except subprocess.CalledProcessError:
        # Final fallback: just core
        warn("Extra dependencies failed, installing core only...")
        subprocess.run(
            [str(UV_PATH), "pip", "install", "-e", str(hermes_src),
             "--python", str(python_in_venv)],
            check=True
        )
        success("Installed core dependencies only.")

def create_config():
    """Create default configuration files."""
    env_file = DATA_DIR / ".env"
    if not env_file.exists():
        info("Creating default .env...")
        env_file.write_text("""# Hermes Portable - Environment Variables
# Add your API keys here (uncomment and fill in)

# OPENROUTER_API_KEY=your_key_here
# ANTHROPIC_API_KEY=your_key_here
# OPENAI_API_KEY=your_key_here
# GOOGLE_API_KEY=your_key_here
# DEEPSEEK_API_KEY=your_key_here
""")
        success("Default .env created.")

    config_file = DATA_DIR / "config.yaml"
    if not config_file.exists():
        info("Creating default config.yaml...")
        config_file.write_text("""# Hermes Portable Configuration
model:
  default: "openrouter/anthropic/claude-sonnet-4"
  provider: "openrouter"

terminal:
  backend: "local"
  timeout: 180

compression:
  enabled: true
  threshold: 0.50
  target_ratio: 0.20

display:
  skin: "default"
  tool_progress: true
  show_cost: true

memory:
  memory_enabled: true
  user_profile_enabled: true
""")
        success("Default config.yaml created.")

def main():
    banner()

    try:
        setup_directories()
        install_uv()
        install_python()

        python_bin = find_python()
        if not python_bin:
            error("Could not find installed Python. Setup failed.")
            sys.exit(1)
        success(f"Python found: {python_bin}")

        clone_hermes()
        create_venv(python_bin)
        install_deps()
        create_config()

        print(f"""
{GREEN}{BOLD}
  ╔═══════════════════════════════════╗
  ║      Setup Complete! ✓            ║
  ╚═══════════════════════════════════╝
{RESET}
  Next steps:
  1. Edit {CYAN}data/.env{RESET} to add your API keys
  2. Run {CYAN}./start.sh{RESET} (or {CYAN}start.bat{RESET} on Windows)
  
  Enjoy your portable AI agent! 🚀
""")

    except KeyboardInterrupt:
        print("\n\nSetup interrupted.")
        sys.exit(130)
    except Exception as e:
        error(f"Setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
