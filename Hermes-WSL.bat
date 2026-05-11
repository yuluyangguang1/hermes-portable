@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

rem ═══════════════════════════════════════════════════════
rem  Hermes Portable — WSL2 fallback launcher
rem  Only use this if Hermes.bat (native) fails on your
rem  Windows setup. Requires WSL2 + Ubuntu or similar.
rem ═══════════════════════════════════════════════════════

set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

rem ── WSL availability ────────────────────────────────────
wsl --version >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo   WSL2 is not installed.
    echo.
    echo   Install it:  wsl --install  ^(run PowerShell as admin, then reboot^)
    echo   Or use native launcher:  Hermes.bat
    echo.
    pause
    exit /b 1
)

rem ── HOME hijack sandbox ────────────────────────────────
rem  Create the junction from the Windows side — WSL2 follows NTFS
rem  reparse points transparently through /mnt/c/..., so a single
rem  sandbox works for both launchers. See Hermes.bat for the long
rem  explanation; the logic below is a condensed version.
if not exist "%HERE%\data" mkdir "%HERE%\data" >nul 2>&1
set "SANDBOX=%HERE%\_home"
if not exist "%SANDBOX%" mkdir "%SANDBOX%" >nul 2>&1
set "LINK=%SANDBOX%\.hermes"
if not exist "%LINK%" goto :wsl_create_junction

dir /AL "%SANDBOX%" 2>nul | findstr /I /C:".hermes" >nul
if !errorlevel! equ 0 goto :wsl_junction_ok

rem Not a reparse point. Try to delete as a plain file first.
del "%LINK%" >nul 2>&1
if not exist "%LINK%" goto :wsl_create_junction

echo.
echo   [ERROR] %LINK% exists but is not a junction.
echo   Remove it first:  rmdir /S /Q "%LINK%"
echo.
pause
exit /b 1

:wsl_create_junction
mklink /J "%LINK%" "%HERE%\data" >nul 2>&1
if !errorlevel! equ 0 goto :wsl_junction_ok
mklink /D "%LINK%" "%HERE%\data" >nul 2>&1
if !errorlevel! equ 0 goto :wsl_junction_ok
echo.
echo   [ERROR] Could not create %LINK%.
echo   Drive may be FAT32/exFAT. Move HermesPortable to NTFS
echo   or enable Windows Developer Mode.
echo.
pause
exit /b 1

:wsl_junction_ok

rem ── Convert Windows path to WSL path ────────────────────
for /f "usebackq delims=" %%I in (`wsl wslpath "%HERE%"`) do set "WSL_HERE=%%I"
if not defined WSL_HERE (
    echo   [ERROR] Could not convert path: %HERE%
    pause
    exit /b 1
)

rem ── Pick a Linux venv directory ────────────────────────
set "WSL_VENV="
for %%D in (venv-linux-x64 venv) do (
    wsl test -x "%WSL_HERE%/%%D/bin/hermes" 2>nul
    if !errorlevel! equ 0 (
        set "WSL_VENV=%WSL_HERE%/%%D"
        goto :venv_found
    )
)
echo.
echo   [ERROR] Linux venv not found in WSL.
echo.
echo   Expected one of:
echo     %WSL_HERE%/venv-linux-x64/bin/hermes
echo     %WSL_HERE%/venv/bin/hermes
echo.
echo   Note: the Universal zip ships a Linux venv that works in WSL,
echo   but a Windows-only zip will NOT.
echo.
pause
exit /b 1
:venv_found

echo.
echo   Hermes Portable (via WSL2)
echo   --------------------------
echo.

rem ── First-run / explicit config mode ───────────────────
rem Escape single quotes in WSL_HERE to prevent injection into bash -c
set "WSL_HERE_SAFE=!WSL_HERE:'='\''!"
set "WSL_VENV_SAFE=!WSL_VENV:'='\''!"

set "HAS_KEY=false"
wsl test -f "%WSL_HERE%/data/.env" 2>nul
if !errorlevel! equ 0 (
    wsl grep -qE "^[A-Z_]+_API_KEY=.{10,}" "%WSL_HERE%/data/.env" 2>nul
    if !errorlevel! equ 0 set "HAS_KEY=true"
)

if /I "%~1"=="--config" goto :run_config
if "%HAS_KEY%"=="false" goto :run_config
goto :run_hermes

:run_config
echo   Opening config panel at http://127.0.0.1:17520 ...
start "" "http://127.0.0.1:17520"
wsl bash -c "cd '!WSL_HERE_SAFE!' && export HOME='!WSL_HERE_SAFE!/_home' && export HERMES_HOME='!WSL_HERE_SAFE!/data' && '!WSL_VENV_SAFE!/bin/python' '!WSL_HERE_SAFE!/config_server.py'"
set "EXITCODE=%errorlevel%"
goto :done

:run_hermes
rem Best-effort webui launch. We do NOT trust the exit code of the
rem backgrounded subshell (it always returns 0), so we only open the
rem browser after a short sleep that lets it bind the port.
wsl bash -c "command -v hermes-web-ui >/dev/null 2>&1 && (export HOME='!WSL_HERE_SAFE!/_home' PATH='!WSL_HERE_SAFE!/node/bin:$PATH' HERMES_HOME='!WSL_HERE_SAFE!/data' && nohup hermes-web-ui start --port 8648 >/dev/null 2>&1 &)" 2>nul

wsl bash -c "cd '!WSL_HERE_SAFE!' && export HOME='!WSL_HERE_SAFE!/_home' && export HERMES_HOME='!WSL_HERE_SAFE!/data' && export PATH='!WSL_VENV_SAFE!/bin:!WSL_HERE_SAFE!/node/bin:$PATH' && '!WSL_VENV_SAFE!/bin/hermes' %*"
set "EXITCODE=%errorlevel%"
goto :done

:done
if not "%EXITCODE%"=="0" (
    echo.
    echo   Hermes exited with code %EXITCODE%.
    pause
)
endlocal & exit /b %EXITCODE%
