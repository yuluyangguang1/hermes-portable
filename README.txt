Hermes Portable
===============

  Plug-in-a-USB AI Agent — no installer, no admin rights, no host-side config.

How to run
----------
  macOS    →  double-click  Hermes.command
  Windows  →  double-click  Hermes.bat

On first run a config panel opens at http://127.0.0.1:17520 for
you to paste an API key. After that, the launcher starts Hermes directly.

Package layouts
---------------
  Platform zip (HermesPortable-macOS.zip / Windows):
      venv/, python/, node/             ← generic names, launcher finds them

  Universal zip (HermesPortable-Universal.zip):
      venv-macos-arm64/, python-macos-arm64/, node-macos-arm64/
      venv-windows-x64/, python-windows-x64/, node-windows-x64/
      → same launchers auto-pick the right set for the host

You never need to touch those directories. Use `data/` for everything.

Windows notes
-------------
  • Windows native support is stable (upstream Hermes Agent docs
    removed the Beta tag at v0.14.0). The launcher runs hermes
    directly via venv\Scripts\hermes.exe — no WSL required.
  • SmartScreen will warn "Unknown publisher" on first run —
    click "More info" → "Run anyway".
  • Hermes-WSL.bat is still shipped as an optional path: use it if
    you want POSIX-only features (e.g. dashboard's embedded /chat
    terminal pane, which needs a POSIX PTY) or if your machine
    blocks something the native path needs.
  • Prefer short install paths (e.g. C:\HP) — long paths can trip up
    older Python packages on Windows.

macOS notes
-----------
  • GitHub CI builds on macos-latest, which is ARM64 (Apple Silicon).
    Intel Mac users should either build from source (`python3 tools/build.py`)
    or use the Universal zip once both arch builds land in it.

macOS notes
-----------
  • Recommended: macOS 13.5+ (Ventura). Node.js 24 binaries are stamped
    with minos 13.5, so Apple won't officially support older versions.
  • Older macOS (10.15 Catalina through 12 Monterey) often still works:
    Node only depends on libSystem, libc++, CoreFoundation, Security —
    all stable since macOS 10.x. If startup fails on an older host with
    a "dyld: missing symbol" error, upgrade macOS or rebuild Hermes
    from source on that machine.

Windows notes
-------------
  • Windows 10 / 11 (x64). On ARM hardware, the bundled x64 Node runs
    under Prism emulation — performance is fine for the web UI.

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
      python lib/update.py update

Building from source
--------------------
  python3 tools/build.py                     (platform zip for current OS)
  python3 tools/build.py --layout universal  (per-platform-suffixed dirs, for Universal)

License: MIT
