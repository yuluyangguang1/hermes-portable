@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

rem ═══════════════════════════════════════════════════════
rem  Hermes Portable — Windows native launcher
rem ═══════════════════════════════════════════════════════

set "HERE=%~dp0"
rem %~dp0 ends with backslash; strip it for consistency
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

rem ── Multi-layout venv detection ────────────────────────
rem  Universal / per-platform layouts all supported:
rem    HermesPortable\venv-windows-x64\Scripts\hermes.exe   (Universal)
rem    HermesPortable\venv\Scripts\hermes.exe               (platform-only)
if exist "%HERE%\venv-windows-x64\Scripts\hermes.exe" (
    set "VENV_DIR=%HERE%\venv-windows-x64"
    set "PYTHON_DIR=%HERE%\python-windows-x64"
) else if exist "%HERE%\venv\Scripts\hermes.exe" (
    set "VENV_DIR=%HERE%\venv"
    set "PYTHON_DIR=%HERE%\python"
) else (
    echo.
    echo   [ERROR] Windows venv not found.
    echo.
    echo   Expected one of:
    echo     %HERE%\venv-windows-x64\Scripts\hermes.exe
    echo     %HERE%\venv\Scripts\hermes.exe
    echo.
    echo   If you downloaded the Universal zip, make sure the Windows
    echo   sub-archive was extracted. Otherwise rebuild with:
    echo     python build.py
    echo.
    pause
    exit /b 1
)

rem Node runtime (Universal packs it under node-windows-x64)
if exist "%HERE%\node-windows-x64" (
    set "NODE_DIR=%HERE%\node-windows-x64"
) else if exist "%HERE%\node" (
    set "NODE_DIR=%HERE%\node"
) else (
    set "NODE_DIR="
)

rem ── HOME hijack sandbox ────────────────────────────────
rem  %HERE%\_home acts as a private HOME. %HERE%\_home\.hermes is a
rem  directory junction (mklink /J) pointing to %HERE%\data, so any
rem  tool that reads or writes %USERPROFILE%\.hermes (hermes-web-ui,
rem  some plugins, …) lands inside the portable folder instead.
rem  The host's real %USERPROFILE%\.hermes is never touched.
rem
rem  Junctions work on NTFS without admin. If the U-stick is formatted
rem  FAT32/exFAT, junctions are not supported — we fall back to a
rem  symlink (needs Developer Mode or admin). If both fail we bail out.
if not exist "%HERE%\data" mkdir "%HERE%\data" >nul 2>&1
set "SANDBOX=%HERE%\_home"
if not exist "%SANDBOX%" mkdir "%SANDBOX%" >nul 2>&1

set "LINK=%SANDBOX%\.hermes"
rem  Detect what's currently at LINK:
rem    missing            → create junction
rem    reparse point      → already a link, leave as-is (idempotent)
rem    real directory     → refuse to clobber, tell user
if exist "%LINK%" (
    rem Check reparse-point attribute (junctions + symlinks both have it)
    dir /AL "%SANDBOX%" 2>nul | findstr /I /C:".hermes" >nul
    if !errorlevel! neq 0 (
        echo.
        echo   [ERROR] %LINK% exists as a real directory.
        echo   The sandbox expects a junction here.
        echo.
        echo   Back up anything inside, then remove it:
        echo     rmdir /S /Q "%LINK%"
        echo.
        pause
        exit /b 1
    )
) else (
    rem Try junction first (NTFS, no admin needed)
    mklink /J "%LINK%" "%HERE%\data" >nul 2>&1
    if !errorlevel! neq 0 (
        rem Fall back to directory symlink (needs Dev Mode / admin)
        mklink /D "%LINK%" "%HERE%\data" >nul 2>&1
        if !errorlevel! neq 0 (
            echo.
            echo   [ERROR] Could not create link:
            echo     %LINK%  ^>  %HERE%\data
            echo.
            echo   Your drive may be FAT32/exFAT and not support junctions.
            echo   Try one of:
            echo     * Copy HermesPortable to an NTFS drive, OR
            echo     * Enable Windows Developer Mode and rerun.
            echo.
            pause
            exit /b 1
        )
    )
)

rem ── Environment ────────────────────────────────────────
rem  Override HOME *and* USERPROFILE — different libs read different
rem  vars (Python's os.path.expanduser on Windows prefers USERPROFILE,
rem  Node/npm frequently reads HOME).
set "HOME=%SANDBOX%"
set "USERPROFILE=%SANDBOX%"
set "HERMES_HOME=%HERE%\data"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
if defined NODE_DIR (
    set "PATH=%VENV_DIR%\Scripts;%NODE_DIR%;%PYTHON_DIR%;%PATH%"
) else (
    set "PATH=%VENV_DIR%\Scripts;%PYTHON_DIR%;%PATH%"
)

rem ── Single-instance lock (best-effort) ─────────────────
rem cmd.exe has no cheap way to record its own PID, so this lock is a
rem "stale-file" marker, not a PID check. If you see this error and are
rem sure no other instance is running, just delete the lock file.
set "LOCK_FILE=%HERE%\data\.hermes.lock"
if not exist "%HERE%\data" mkdir "%HERE%\data" >nul 2>&1

if exist "%LOCK_FILE%" (
    echo.
    echo   Another Hermes launcher appears to already be running.
    echo.
    echo   If that is wrong, delete this file and try again:
    echo     %LOCK_FILE%
    echo.
    timeout /t 5 /nobreak >nul
    exit /b 1
)

echo.
echo   Hermes Portable
echo   ---------------
echo.

rem ── First-run detection ────────────────────────────────
set "HAS_KEY=false"
if exist "%HERE%\data\.env" (
    findstr /R "^[A-Z_][A-Z_]*_API_KEY=..........*" "%HERE%\data\.env" >nul 2>&1
    if !errorlevel! equ 0 set "HAS_KEY=true"
)

rem Config-panel mode: either explicit --config flag, or missing key
if /I "%~1"=="--config" goto :run_config
if "%HAS_KEY%"=="false" goto :run_config

goto :run_hermes

:run_config
echo   Opening config panel at http://127.0.0.1:17520 ...
echo.
start "" "http://127.0.0.1:17520"
"%VENV_DIR%\Scripts\python.exe" "%HERE%\config_server.py"
set "EXITCODE=%errorlevel%"
goto :cleanup

:run_hermes
rem Best-effort background web UI (if user installed hermes-web-ui)
where hermes-web-ui >nul 2>&1
if !errorlevel! equ 0 (
    start "" /b cmd /c "hermes-web-ui start --port 8648 >nul 2>&1"
)

rem Record something identifiable for the lock (cmd does not expose its
rem own PID without extra hacks; a random token is good enough to tell
rem us "a launcher was started and did not clean up").
echo %TIME%-%RANDOM% > "%LOCK_FILE%"

"%VENV_DIR%\Scripts\hermes.exe" %*
set "EXITCODE=%errorlevel%"
goto :cleanup

:cleanup
del "%LOCK_FILE%" >nul 2>&1
del "%LOCK_FILE%.tmp" >nul 2>&1

rem Pause only on non-zero exit so the user can read the error
if not "%EXITCODE%"=="0" (
    echo.
    echo   Hermes exited with code %EXITCODE%.
    pause
)
endlocal & exit /b %EXITCODE%
