#!/usr/bin/env python3
"""
fix_shims.py - self-heal uv trampoline entry points for Hermes Portable.

Why this exists
---------------
uv installs Windows entry-point scripts (hermes.exe, config_server.exe, etc.)
as compact "trampoline" .exe files whose target Python path is stored in a
Windows PE resource (RT_RCDATA / UV_PYTHON_PATH), NOT as a `#!` shebang.

When the Hermes Portable zip is built on GitHub Actions, the path baked
into those trampolines is the CI runner's absolute path:

    D:\a\hermes-portable\hermes-portable\dist\HermesPortable\python\...

That path does not exist on the user's machine, so double-clicking
Hermes.bat shows:

    No Python at 'D:\a\...\python.exe'

`uv venv --relocatable` marks the *venv* as relocatable (and its own
`venv\Scripts\python.exe` trampoline gets a relative path at create
time), but older uv builds did not propagate that flag to the
entry points created by `uv pip install`. Rather than depend on a
specific uv version, we rewrite those resources ourselves on first
launch.

What we rewrite trampolines TO (and why it matters)
---------------------------------------------------
We point entry-point trampolines at the VENV's python.exe
(venv\Scripts\python.exe), NOT the base python directly.

The venv's python.exe is itself a uv trampoline (created by
`uv venv --relocatable`) that forwards to the base python with
`pyvenv.cfg home=<base>` and `VIRTUAL_ENV=<venv>` in effect -- so
CPython initializes `sys.prefix = <venv>`, and
`venv\Lib\site-packages` ends up on `sys.path`. That is how
`import hermes_cli` succeeds.

v0.13.7 got this wrong: it pointed entry-points at the base
python directly, so `sys.prefix` resolved to the base python
install, venv site-packages was NOT on sys.path, and launching
Hermes.bat crashed with:

    ModuleNotFoundError: No module named 'hermes_cli'

v0.13.8 rewrites entry points to `venv\Scripts\python.exe` via a
relative path (usually just "python.exe" since they're siblings),
so the whole venv stays USB-portable across drive letters.

What we do (Windows)
--------------------
Use ctypes to call the same Win32 APIs uv itself uses:
  - BeginUpdateResourceW
  - UpdateResourceW   (RT_RCDATA, name=UV_PYTHON_PATH, data=<new path utf8>)
  - EndUpdateResourceW
This updates both the resource data AND its size atomically, keeping
the PE file well-formed.

We also fix pyvenv.cfg's `home =` line if it points at a missing
path. `home` must point at the BASE python directory (not the venv),
because that is how CPython locates the real interpreter.

What we do (Unix)
-----------------
uv on macOS/Linux uses text shebangs in `venv/bin/*`. For relocatable
venvs these already use `/bin/sh + $(realpath)` tricks, but in case a
build shipped absolute shebangs, we rewrite the first line to point
at the venv's python (bin/python), which is a symlink to the base
python configured as a venv.

Idempotent: re-running is a no-op once paths already match.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


# ─── Path discovery ───────────────────────────────────────────────────
def _find_first(root: Path, names: tuple[str, ...]) -> Path | None:
    if not root.exists():
        return None
    for p in root.rglob("*"):
        try:
            if p.is_file() and p.name in names:
                return p
        except OSError:
            continue
    return None


def find_base_python(here: Path) -> Path | None:
    """Locate the BASE (non-venv) portable Python.

    This is what `pyvenv.cfg home =` needs to point at. It is NOT what
    entry-point trampolines should launch directly — see find_venv_python
    for that.
    """
    for name in ("python-windows-x64", "python-windows-arm64",
                 "python-linux-x64", "python-linux-arm64",
                 "python-macos-arm64", "python-macos-x64",
                 "python"):
        d = here / name
        if not d.exists():
            continue
        if sys.platform == "win32":
            p = _find_first(d, ("python.exe",))
        else:
            p = _find_first(d, ("python3.12", "python3.13", "python3", "python"))
        if p is not None:
            return p
    return None


def find_venv_python(venv: Path | None) -> Path | None:
    """Locate the VENV's python -- this is what entry-point trampolines
    must target so that sys.prefix resolves to the venv and
    venv/Lib/site-packages is on sys.path.

    On Windows the venv's python.exe is itself a uv trampoline (created
    by `uv venv --relocatable`) that chain-launches the base python
    with VIRTUAL_ENV / pyvenv.cfg set so imports find hermes_cli.

    If we point hermes.exe directly at the BASE python instead, Python
    runs with sys.prefix = base prefix, venv site-packages is NOT on
    sys.path, and imports of venv-installed packages fail with
    ModuleNotFoundError: No module named 'hermes_cli'. v0.13.7 had
    exactly that bug -- v0.13.8 fixes it.
    """
    if venv is None:
        return None
    if sys.platform == "win32":
        p = venv / "Scripts" / "python.exe"
        return p if p.exists() else None
    for name in ("python", "python3", "python3.12", "python3.13"):
        p = venv / "bin" / name
        if p.exists():
            return p
    return None


def find_venv(here: Path) -> Path | None:
    for name in ("venv-windows-x64", "venv-windows-arm64",
                 "venv-linux-x64", "venv-linux-arm64",
                 "venv-macos-arm64", "venv-macos-x64",
                 "venv"):
        d = here / name
        if d.exists():
            return d
    return None


# ─── Windows PE resource rewrite ──────────────────────────────────────
# Constants matching uv-trampoline-builder/src/lib.rs:
#   RT_RCDATA = 10
#   Resource name = "UV_PYTHON_PATH" (wide string)
RT_RCDATA = 10


def _is_uv_trampoline(path: Path) -> bool:
    """Detect a uv trampoline by reading the UV_PYTHON_PATH resource.

    Returns True iff the .exe is an uv trampoline that has a
    UV_PYTHON_PATH resource we can read.
    """
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    LoadLibraryExW = k32.LoadLibraryExW
    LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
    LoadLibraryExW.restype = wintypes.HMODULE
    FreeLibrary = k32.FreeLibrary
    FreeLibrary.argtypes = [wintypes.HMODULE]
    FreeLibrary.restype = wintypes.BOOL
    FindResourceW = k32.FindResourceW
    FindResourceW.argtypes = [wintypes.HMODULE, wintypes.LPCWSTR, wintypes.LPCWSTR]
    FindResourceW.restype = ctypes.c_void_p

    LOAD_LIBRARY_AS_DATAFILE = 0x00000002
    h = LoadLibraryExW(str(path), None, LOAD_LIBRARY_AS_DATAFILE)
    if not h:
        return False
    try:
        # MAKEINTRESOURCE(RT_RCDATA) — cast int to LPCWSTR
        res = FindResourceW(h, "UV_PYTHON_PATH",
                            ctypes.cast(RT_RCDATA, wintypes.LPCWSTR))
        return bool(res)
    finally:
        FreeLibrary(h)


def _read_uv_python_path(path: Path) -> str | None:
    """Read the current UV_PYTHON_PATH resource as a string, or None."""
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    LoadLibraryExW = k32.LoadLibraryExW
    LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
    LoadLibraryExW.restype = wintypes.HMODULE
    FreeLibrary = k32.FreeLibrary
    FreeLibrary.argtypes = [wintypes.HMODULE]
    FreeLibrary.restype = wintypes.BOOL
    FindResourceW = k32.FindResourceW
    FindResourceW.argtypes = [wintypes.HMODULE, wintypes.LPCWSTR, wintypes.LPCWSTR]
    FindResourceW.restype = ctypes.c_void_p
    SizeofResource = k32.SizeofResource
    SizeofResource.argtypes = [wintypes.HMODULE, ctypes.c_void_p]
    SizeofResource.restype = wintypes.DWORD
    LoadResource = k32.LoadResource
    LoadResource.argtypes = [wintypes.HMODULE, ctypes.c_void_p]
    LoadResource.restype = wintypes.HANDLE
    LockResource = k32.LockResource
    LockResource.argtypes = [wintypes.HANDLE]
    LockResource.restype = ctypes.c_void_p

    LOAD_LIBRARY_AS_DATAFILE = 0x00000002
    h = LoadLibraryExW(str(path), None, LOAD_LIBRARY_AS_DATAFILE)
    if not h:
        return None
    try:
        res = FindResourceW(h, "UV_PYTHON_PATH",
                            ctypes.cast(RT_RCDATA, wintypes.LPCWSTR))
        if not res:
            return None
        size = SizeofResource(h, res)
        if size == 0:
            return None
        hres = LoadResource(h, res)
        if not hres:
            return None
        ptr = LockResource(hres)
        if not ptr:
            return None
        raw = ctypes.string_at(ptr, size)
        try:
            return raw.decode("utf-8").rstrip("\x00")
        except UnicodeDecodeError:
            return None
    finally:
        FreeLibrary(h)


def _write_uv_python_path(path: Path, new_path_utf8: bytes) -> bool:
    """Overwrite the UV_PYTHON_PATH resource in an uv trampoline .exe.

    Uses BeginUpdateResourceW / UpdateResourceW / EndUpdateResourceW —
    the same Win32 APIs uv itself uses when creating trampolines.
    """
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    BeginUpdateResourceW = k32.BeginUpdateResourceW
    BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    BeginUpdateResourceW.restype = wintypes.HANDLE

    UpdateResourceW = k32.UpdateResourceW
    UpdateResourceW.argtypes = [
        wintypes.HANDLE,      # hUpdate
        wintypes.LPCWSTR,     # lpType (MAKEINTRESOURCE cast)
        wintypes.LPCWSTR,     # lpName
        wintypes.WORD,        # wLanguage (0 = neutral)
        ctypes.c_void_p,      # lpData
        wintypes.DWORD,       # cb
    ]
    UpdateResourceW.restype = wintypes.BOOL

    EndUpdateResourceW = k32.EndUpdateResourceW
    EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    EndUpdateResourceW.restype = wintypes.BOOL

    # bDiscard = False: keep existing resources, replace only what we update
    handle = BeginUpdateResourceW(str(path), False)
    if not handle:
        return False
    try:
        buf = ctypes.create_string_buffer(new_path_utf8, len(new_path_utf8))
        ok = UpdateResourceW(
            handle,
            ctypes.cast(RT_RCDATA, wintypes.LPCWSTR),
            "UV_PYTHON_PATH",
            0,  # neutral language — matches what uv writes
            ctypes.cast(buf, ctypes.c_void_p),
            len(new_path_utf8),
        )
        if not ok:
            # Discard changes on failure
            EndUpdateResourceW(handle, True)
            return False
    except Exception:
        EndUpdateResourceW(handle, True)
        return False

    # bDiscard = False: commit
    return bool(EndUpdateResourceW(handle, False))


def fix_windows_trampoline(exe: Path, new_python: Path) -> bool:
    """Rewrite the UV_PYTHON_PATH resource in one trampoline .exe.

    We write a RELATIVE path (relative to the trampoline's own parent
    directory, i.e. venv\\Scripts\\). uv's trampoline code:

        if python_path.is_absolute() { python_path }
        else { executable_name.parent().join(python_path) }

    ...means a relative path follows the folder wherever it moves.
    This makes the zip USB-portable after the first fix — move the
    HermesPortable folder to any drive letter or path and it still
    works, no re-fix needed.

    Returns True iff we actually modified the file.
    Returns False for .exe files that aren't uv trampolines (python.exe,
    pythonw.exe, which are a different trampoline kind) — those we
    leave alone.
    """
    try:
        current = _read_uv_python_path(exe)
    except OSError:
        return False
    if current is None:
        return False  # not a uv trampoline we can/should touch

    # Compute the relative path from the trampoline's dir (venv\Scripts)
    # to the portable python.exe. os.path.relpath handles drive
    # mismatches gracefully in practice — both live under `here`.
    try:
        rel = os.path.relpath(new_python, exe.parent)
    except ValueError:
        # Different drive letters — fall back to absolute.
        rel = str(new_python)

    # If the current resource is already a matching relative path we're
    # done. Also short-circuit when the absolute current path resolves
    # to the same file as our target (some environments write absolute
    # but still point at the real python — no harm).
    if current == rel:
        return False
    try:
        if Path(current).is_absolute() and Path(current).resolve() == new_python.resolve():
            # Already valid — leave it alone.
            return False
    except (OSError, ValueError):
        pass

    return _write_uv_python_path(exe, rel.encode("utf-8"))


# ─── Unix shebang rewrite ─────────────────────────────────────────────
# Linux's BINPRM_BUF_SIZE truncates `#!` lines past 128 bytes, and the
# limit includes the "#!" and trailing newline. macOS is more generous
# (512 bytes) but not infinite. If the portable folder lives at a long
# path (e.g. an NFS mount or a deep USB label on Windows-portable Linux),
# rewriting the shebang to an absolute interpreter path could push the
# first line over the limit, at which point exec() returns ENOEXEC and
# the entry-point script breaks in a confusing way (user sees "python:
# can't open file" because the kernel silently lopped the path).
#
# Safe threshold: 124 bytes of "#!…\n", giving us a small buffer under
# Linux's 128. If the direct shebang would exceed that, fall back to
# the /bin/sh exec-wrapper pattern — still a valid interpreter line,
# but the long path lives in the script body where there's no length
# cap. The wrapper is what uv itself emits for `uv venv --relocatable`
# on Unix, so it's been exercised by every relocatable venv out there.
SHEBANG_BYTE_LIMIT = 124


def fix_text_shebang(path: Path, new_python: Path) -> bool:
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if not data.startswith(b"#!"):
        return False
    nl = data.find(b"\n")
    if nl < 0:
        return False
    first = data[2:nl].strip()
    # Only rewrite simple python shebangs. Skip `/bin/sh` wrappers that
    # uv emits for relocatable venvs — those already work.
    basename = first.split(b"/")[-1].strip()
    if not basename.startswith((b"python", b"pypy")):
        return False

    py_path_bytes = str(new_python).encode("utf-8")
    direct_sheb = b"#!" + py_path_bytes + b"\n"

    if len(direct_sheb) <= SHEBANG_BYTE_LIMIT:
        new_line = direct_sheb
    else:
        # Too long for the kernel's buffer. Build a sh-exec wrapper
        # that (a) is a 1-line /bin/sh shebang (tiny) and (b) re-execs
        # python on itself with the original script's body passed as
        # stdin. `"""":"` starts a Python docstring that swallows the
        # shell line so Python parses from `exec "$@"` onward harmlessly.
        #
        # This mirrors what uv, pipx and Homebrew Python venvs do when
        # a target path is too long. Body stays intact; only the first
        # line changes.
        body = data[nl + 1:]
        # Two-line prelude:
        #   #!/bin/sh
        #   '''exec' "<python>" "$0" "$@"
        #   ' '''
        # The `'''exec'` is a Python string literal that shell sees as
        # a normal command. The closing `' '''` on the next line ends
        # the Python string. Then the real Python body starts.
        new_line = (
            b"#!/bin/sh\n"
            b"'''exec' " + py_path_bytes + b' "$0" "$@"\n'
            b"' '''\n"
        )
        body = data[nl + 1:]
        try:
            path.write_bytes(new_line + body)
            os.chmod(path, 0o755)
        except OSError:
            return False
        return True

    if data[:nl + 1] == new_line:
        return False
    try:
        path.write_bytes(new_line + data[nl + 1:])
        os.chmod(path, 0o755)
    except OSError:
        return False
    return True


# ─── pyvenv.cfg ───────────────────────────────────────────────────────
def fix_pyvenv_cfg(venv: Path, python: Path) -> bool:
    cfg = venv / "pyvenv.cfg"
    if not cfg.exists():
        return False
    try:
        text = cfg.read_text(encoding="utf-8")
    except OSError:
        return False
    new_home = str(python.parent)
    lines = text.splitlines()
    changed = False
    for i, line in enumerate(lines):
        s = line.strip()
        if "=" not in s:
            continue
        key, _, value = s.partition("=")
        if key.strip().lower() == "home":
            cur = value.strip()
            if cur != new_home and not Path(cur).exists():
                lines[i] = f"home = {new_home}"
                changed = True
                break
    if changed:
        try:
            cfg.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            return False
    return changed


# ─── entry ────────────────────────────────────────────────────────────
def main() -> int:
    here = Path(__file__).resolve().parent
    venv = find_venv(here)
    base_python = find_base_python(here)
    venv_python = find_venv_python(venv)
    if venv is None or base_python is None or venv_python is None:
        # Nothing sensible to do — launcher itself will report a clearer
        # layout error. Exit 0 so we don't block the launcher.
        return 0

    is_windows = sys.platform == "win32" and (venv / "Scripts").exists()
    scripts = venv / ("Scripts" if is_windows else "bin")
    if not scripts.exists():
        return 0

    rewrote = 0
    if is_windows:
        # Point entry-point trampolines at the VENV's python.exe, which
        # is itself a uv-built trampoline that forwards to the base
        # python with pyvenv.cfg / sys.prefix configured so that
        # venv\Lib\site-packages is importable. Pointing directly at
        # the base python (as v0.13.7 did) broke hermes_cli imports.
        for exe in sorted(scripts.glob("*.exe")):
            # Skip the base-python trampolines themselves:
            #   - python.exe, pythonw.exe, python3.exe are managed by
            #     `uv venv --relocatable` and should not be self-referential
            #   - fixing them with a path to themselves would create a
            #     launch loop.
            if exe.name.lower() in ("python.exe", "pythonw.exe", "python3.exe"):
                continue
            try:
                if fix_windows_trampoline(exe, venv_python):
                    rewrote += 1
            except Exception:
                # Defense in depth — never let shim repair crash the launcher.
                continue
    else:
        # On Unix, venv shebangs should also point at the venv python
        # (bin/python, which is a symlink to the base python) so
        # sys.prefix resolves to the venv.
        for f in sorted(scripts.iterdir()):
            try:
                if not f.is_file() or f.is_symlink():
                    continue
                if fix_text_shebang(f, venv_python):
                    rewrote += 1
            except Exception:
                continue

    # pyvenv.cfg's `home =` key points at the BASE python directory,
    # not the venv. That's how CPython locates the real interpreter
    # when the venv's python.exe runs.
    try:
        fix_pyvenv_cfg(venv, base_python)
    except Exception:
        pass

    if rewrote:
        print(f"[fix_shims] rewrote {rewrote} launcher(s) -> {venv_python}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
