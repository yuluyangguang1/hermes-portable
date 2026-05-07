#!/usr/bin/env python3
"""
Hermes Portable — 自动更新工具
检查并更新 hermes-agent 到最新版本

用法:
  python3 update.py check     # 检查是否有新版本
  python3 update.py update    # 更新到最新版本
  python3 update.py status    # 显示当前版本信息
"""
import json
import os
import subprocess
import sys
import urllib.request
import shutil
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.resolve()
HERMES_DIR = SCRIPT_DIR / "hermes-agent"
VENV_DIR = SCRIPT_DIR / "venv"

# ANSI colors
G = "\033[92m"
R = "\033[91m"
Y = "\033[93m"
C = "\033[96m"
B = "\033[1m"
X = "\033[0m"


def get_local_version():
    """Get the locally installed hermes version."""
    # Try reading from the installed package
    hermes_bin = VENV_DIR / "bin" / "hermes"
    if not hermes_bin.exists():
        return None
    try:
        r = subprocess.run(
            [str(hermes_bin), "--version"],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, "HERMES_HOME": str(SCRIPT_DIR / "data")},
        )
        # Parse "Hermes Agent v0.9.0 (2026.4.13)" from output
        for line in r.stdout.splitlines():
            if "Hermes Agent" in line and "v" in line:
                return line.strip()
    except Exception:
        pass

    # Fallback: check git commit
    if (HERMES_DIR / ".git").exists():
        try:
            r = subprocess.run(
                ["git", "-C", str(HERMES_DIR), "log", "-1", "--format=%H %ci"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                parts = r.stdout.strip().split(" ", 1)
                return f"commit {parts[0][:8]} ({parts[1][:10] if len(parts) > 1 else 'unknown'})"
        except Exception:
            pass

    # Fallback: check file modification time
    setup_py = HERMES_DIR / "setup.py"
    pyproject = HERMES_DIR / "pyproject.toml"
    ref = pyproject if pyproject.exists() else setup_py
    if ref.exists():
        mtime = datetime.fromtimestamp(ref.stat().st_mtime)
        return f"local build ({mtime.strftime('%Y-%m-%d')})"

    return "unknown"


def get_remote_version():
    """Get the latest version from GitHub."""
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/NousResearch/hermes-agent/commits?per_page=1",
            headers={"User-Agent": "HermesPortable/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data:
                commit = data[0]
                sha = commit["sha"][:8]
                date = commit["commit"]["committer"]["date"][:10]
                msg = commit["commit"]["message"].split("\n")[0][:60]
                return {"sha": sha, "date": date, "message": msg}
    except Exception as e:
        return {"error": str(e)}
    return {"error": "no data"}


def check_update():
    """Check if an update is available. Returns dict with status."""
    local = get_local_version()
    remote = get_remote_version()

    result = {
        "local_version": local,
        "remote": remote,
        "update_available": False,
    }

    if "error" in remote:
        result["status"] = "error"
        result["message"] = f"Cannot check updates: {remote['error']}"
        return result

    # Compare by date if possible
    if local and "20" in str(local):
        # Extract date from local version string
        import re
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", str(local))
        if date_match:
            local_date = date_match.group(1)
            if remote["date"] > local_date:
                result["update_available"] = True
                result["status"] = "update_available"
                result["message"] = f"New version available: {remote['date']} ({remote['sha']})"
                return result

    # Compare by commit hash for git clones
    if (HERMES_DIR / ".git").exists():
        try:
            r = subprocess.run(
                ["git", "-C", str(HERMES_DIR), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            local_sha = r.stdout.strip()[:8] if r.returncode == 0 else ""
            if local_sha and remote["sha"] != local_sha:
                result["update_available"] = True
                result["status"] = "update_available"
                result["message"] = f"New commit available: {remote['sha']}"
                return result
        except Exception:
            pass

    result["status"] = "up_to_date"
    result["message"] = "You are running the latest version"
    return result


def do_update():
    """Pull latest hermes-agent and reinstall deps."""
    if not (HERMES_DIR / ".git").exists():
        print(f"{R}✗ hermes-agent is not a git clone, cannot update{X}")
        print(f"  Rebuild with: python3 build.py")
        return False

    # Backup before update
    print(f"\n{C}[0/3] Creating backup...{X}")
    backup_dir = SCRIPT_DIR / "data" / ".update_backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"pre_update_{ts}"
    try:
        shutil.copytree(HERMES_DIR, backup_path, ignore=shutil.ignore_patterns(
            "__pycache__", ".git", "node_modules", "venv", "*.pyc"
        ))
        print(f"{G}✓ Backup: {backup_path}{X}")
    except Exception as e:
        print(f"{Y}⚠ Backup failed ({e}), continuing anyway...{X}")

    print(f"\n{C}[1/3] Pulling latest changes...{X}")
    r = subprocess.run(
        ["git", "-C", str(HERMES_DIR), "pull", "--ff-only"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        if "Already up to date" in r.stdout:
            print(f"{G}✓ Already up to date{X}")
            return True
        print(f"{R}✗ Git pull failed:{X}\n{r.stderr}")
        return False
    print(f"{G}✓ {r.stdout.strip()}{X}")

    print(f"\n{C}[2/3] Cleaning build artifacts...{X}")
    # Remove __pycache__ from hermes-agent
    for d in HERMES_DIR.rglob("__pycache__"):
        import shutil
        shutil.rmtree(d, ignore_errors=True)
    print(f"{G}✓ Cleaned{X}")

    print(f"\n{C}[3/3] Reinstalling dependencies...{X}")
    py_venv = VENV_DIR / "bin" / "python"
    if not py_venv.exists():
        py_venv = VENV_DIR / "Scripts" / "python.exe"

    r = subprocess.run(
        [str(py_venv), "-m", "pip", "install", "-e", str(HERMES_DIR)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"{Y}⚠ pip install had warnings, trying with --no-deps...{X}")
        subprocess.run(
            [str(py_venv), "-m", "pip", "install", "-e", str(HERMES_DIR), "--no-deps"],
            capture_output=True,
        )

    print(f"{G}✓ Dependencies updated{X}")
    print(f"\n{G}{B}  ✓ UPDATE COMPLETE{X}")
    print(f"  New version: {get_local_version()}\n")
    return True


def main():
    if len(sys.argv) < 2:
        cmd = "status"
    else:
        cmd = sys.argv[1].lower()

    if cmd == "status":
        local = get_local_version()
        print(f"\n{B}Hermes Portable — Version Info{X}\n")
        print(f"  Local:  {C}{local}{X}")
        print(f"  Path:   {C}{HERMES_DIR}{X}")
        if (HERMES_DIR / ".git").exists():
            print(f"  Git:    {G}yes (updatable){X}")
        else:
            print(f"  Git:    {Y}no (rebuild to update){X}")
        print()

    elif cmd == "check":
        result = check_update()
        print(f"\n{B}Update Check{X}\n")
        print(f"  Local:  {C}{result['local_version']}{X}")
        if "error" in result["remote"]:
            print(f"  Remote: {R}Error — {result['remote']['error']}{X}")
        else:
            print(f"  Remote: {C}{result['remote']['date']} ({result['remote']['sha']}) — {result['remote']['message']}{X}")
        if result["update_available"]:
            print(f"\n  {Y}⬆ {result['message']}{X}")
            print(f"  Run: {C}python3 update.py update{X}")
        else:
            print(f"\n  {G}✓ {result['message']}{X}")
        print()

    elif cmd == "update":
        result = check_update()
        if result.get("update_available"):
            do_update()
        elif result["status"] == "up_to_date":
            print(f"\n{G}✓ Already up to date{X}\n")
        else:
            print(f"\n{Y}⚠ Could not check for updates, attempting update anyway...{X}\n")
            do_update()

    elif cmd == "json":
        # Machine-readable output for the config panel API
        result = check_update()
        print(json.dumps(result, ensure_ascii=False))

    else:
        print(f"Usage: {sys.argv[0]} [status|check|update|json]")
        sys.exit(1)


if __name__ == "__main__":
    main()
