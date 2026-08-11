#!/usr/bin/env python3
"""
Cross-platform pre-install of hermes-web-ui for Windows.

GitHub Windows CI runners intermittently suffer a DNS failure (EAI_FAIL)
that prevents `npm install hermes-web-ui` from reaching ANY npm registry,
so the Windows package can never be built on CI. However, the Mac/Linux
runners CAN reach npm. hermes-web-ui and its native modules
(node-pty, sherpa-onnx-node, agent-browser) all ship prebuilt Windows
binaries in their npm tarballs, so we can install the Windows flavor of
the dependency tree on a Mac/Linux machine using `--os=win32 --cpu=x64`
and ship that node_modules inside the Windows package.

This script produces:  <OUT>/node_modules/hermes-web-ui/...
                       <OUT>/package.json   (type:module, for ESM CLI)
which the Windows build consumes as its `node/` content (node.exe is still
provided by the Windows job's own Node.js download, which succeeds).

Usage:
  python3 tools/preinstall_windows_webui.py [--out dist/windows-webui]
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd, env=None, cwd=None):
    print("+ " + " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run(cmd, env=env, cwd=str(cwd) if cwd else None)
    if r.returncode != 0:
        sys.exit(r.returncode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist/windows-webui")
    ap.add_argument("--npm", default="npm")
    args = ap.parse_args()

    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    npm = args.npm
    npm_path = shutil.which(npm)
    env = {**os.environ}
    if npm_path:
        # Prepend the dir containing npm so lifecycle scripts find node/sh
        env["PATH"] = str(Path(npm_path).parent) + os.pathsep + os.environ.get("PATH", "")

    # 1) Install hermes-web-ui for Windows (prebuilt binaries pulled by --os/--cpu)
    run([npm, "install", "hermes-web-ui@latest", "--os=win32", "--cpu=x64",
         "--force", "--no-audit", "--no-fund", "--loglevel=error"],
        env=env, cwd=out)

    # 2) The two optional native deps are skipped by npm on a non-Windows host
    #    (optional + platform-gated). Force them in with the Win32 flag so the
    #    Windows package keeps TTS/ASR (sherpa) and browser automation.
    run([npm, "install", "sherpa-onnx-node", "--os=win32", "--cpu=x64",
         "--force", "--no-audit", "--no-fund", "--loglevel=error"],
        env=env, cwd=out)
    run([npm, "install", "agent-browser", "--os=win32", "--cpu=x64",
         "--force", "--no-audit", "--no-fund", "--loglevel=error"],
        env=env, cwd=out)

    # 3) Write a package.json with type:module so the ESM CLI bin parses.
    pkg = out / "package.json"
    if not pkg.exists():
        pkg.write_text('{"name":"hermes-web-ui-portable","version":"0.0.0","type":"module"}\n')

    # 4) Sanity: the Windows prebuilt binaries must be present.
    webui = out / "node_modules" / "hermes-web-ui"
    if not (webui / "dist" / "server" / "index.js").exists():
        sys.exit(f"❌ hermes-web-ui dist missing in cross-build: {webui}")
    pty_win = list((out / "node_modules" / "node-pty" / "prebuilds").rglob("win32-x64"))
    if not pty_win:
        sys.exit("❌ node-pty win32-x64 prebuilt binary missing — cross-build invalid")
    sherpa_win = list(out.rglob("sherpa-onnx-win-x64"))
    if not sherpa_win:
        print("⚠️  sherpa-onnx-win-x64 not found — TTS/ASR will be unavailable on Windows")

    print(f"✅ Windows webui cross-preinstalled at {out}")
    print(f"   node_modules size: {sum(f.stat().st_size for f in out.rglob('*') if f.is_file()) // 1e6} MB")


if __name__ == "__main__":
    main()
