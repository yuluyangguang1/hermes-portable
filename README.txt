Hermes Portable
===============

  A zero-install AI Agent you can put anywhere — no installer,
  no admin rights, no host-side config. Drop the folder on your
  Desktop, an external drive, or a USB stick, and run it from
  there. All data stays inside the folder.

How to run
----------
  macOS    →  double-click  Hermes.command
  Linux    →  ./Hermes.sh   (from a terminal)
  Windows  →  double-click  Hermes.bat

On first run a config panel opens at http://127.0.0.1:17520 for
you to paste an API key. After that, the launcher starts Hermes directly.

Package layouts
---------------
  Platform zip (HermesPortable-macOS.zip / Linux / Windows):
      venv/, python/, node/             ← generic names, launcher finds them

  Universal zip (HermesPortable-Universal.zip):
      venv-macos-arm64/, python-macos-arm64/, node-macos-arm64/
      venv-linux-x64/,   python-linux-x64/,   node-linux-x64/
      venv-windows-x64/, python-windows-x64/, node-windows-x64/
      → same launchers auto-pick the right set for the host

You never need to touch those directories. Use `data/` for everything.

Windows notes
-------------
  • Windows native support is Early Beta.
  • SmartScreen will warn "Unknown publisher" on first run —
    click "More info" → "Run anyway".
  • If anything misbehaves, try Hermes-WSL.bat (WSL2 fallback).
    The Universal zip carries a Linux venv that WSL can use directly.
  • Prefer short install paths (e.g. C:\HP) — long paths can trip up
    older Python packages on Windows.

macOS notes
-----------
  • GitHub CI builds on macos-latest, which is ARM64 (Apple Silicon).
    Intel Mac users should either build from source (`python3 build.py`)
    or use the Universal zip once both arch builds land in it.

Linux notes
-----------
  • Requires glibc ≥ 2.28 (Ubuntu 20.04+, Debian 11+, RHEL 8+).
    Node.js 22.x's prebuilt binaries won't run on older glibc.
  • If `Hermes.sh` fails with `GLIBC_2.xx not found`, run
    `./linux-rebuild.sh` on the target machine to rebuild the runtime.

Data layout
-----------
  data/             all user state (sessions, skills, logs)
  data/.env         API keys
  data/config.yaml  settings

Update
------
  Open the config panel (any launcher with --config, or first run) and
  click "Check for Updates" in the bottom right.
  Or from a terminal:
      python update.py update

Building from source
--------------------
  python3 build.py                     (platform zip for current OS)
  python3 build.py --layout universal  (per-platform-suffixed dirs, for Universal)

License: MIT
