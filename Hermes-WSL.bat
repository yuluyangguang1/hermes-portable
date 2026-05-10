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
wsl bash -c "cd '!WSL_HERE_SAFE!' && export HERMES_HOME='!WSL_HERE_SAFE!/data' && '!WSL_VENV_SAFE!/bin/python' '!WSL_HERE_SAFE!/config_server.py'"
set "EXITCODE=%errorlevel%"
goto :done

:run_hermes
rem Best-effort webui launch. We do NOT trust the exit code of the
rem backgrounded subshell (it always returns 0), so we only open the
rem browser after a short sleep that lets it bind the port.
wsl bash -c "command -v hermes-web-ui >/dev/null 2>&1 && (export PATH='!WSL_HERE_SAFE!/node/bin:$PATH' HERMES_HOME='!WSL_HERE_SAFE!/data' && nohup hermes-web-ui start --port 8648 >/dev/null 2>&1 &)" 2>nul

wsl bash -c "cd '!WSL_HERE_SAFE!' && export HERMES_HOME='!WSL_HERE_SAFE!/data' && export PATH='!WSL_VENV_SAFE!/bin:!WSL_HERE_SAFE!/node/bin:$PATH' && '!WSL_VENV_SAFE!/bin/hermes' %*"
set "EXITCODE=%errorlevel%"
goto :done

:done
if not "%EXITCODE%"=="0" (
    echo.
    echo   Hermes exited with code %EXITCODE%.
    pause
)
endlocal & exit /b %EXITCODE%
