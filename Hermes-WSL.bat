@echo off
rem IMPORTANT: this file MUST stay pure ASCII (see Hermes.bat top of file).
rem Non-ASCII in rem comments on a GBK Windows can chop into stray ')' or
rem '"' bytes and break the if-block parser.
chcp 65001 >nul
setlocal enabledelayedexpansion

rem =======================================================
rem  Hermes Portable - WSL2 fallback launcher
rem  Only use this if Hermes.bat (native) fails on your
rem  Windows setup. Requires WSL2 + Ubuntu or similar.
rem =======================================================

set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

rem -- WSL availability -----------------------------------
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

rem -- HOME hijack sandbox --------------------------------
rem  Create the junction from the Windows side -- WSL2 follows NTFS
rem  reparse points transparently through /mnt/c/..., so a single
rem  sandbox works for both launchers. See Hermes.bat for the long
rem  explanation; the logic below is a condensed version.
if not exist "%HERE%\data" mkdir "%HERE%\data" >nul 2>&1
set "SANDBOX=%HERE%\_home"
if not exist "%SANDBOX%" mkdir "%SANDBOX%" >nul 2>&1
set "LINK=%SANDBOX%\.hermes"
if exist "%LINK%" (
    dir /AL "%SANDBOX%" 2>nul | findstr /I /C:".hermes" >nul
    if !errorlevel! neq 0 (
        echo.
        echo   [ERROR] %LINK% exists as a real directory, not a junction.
        echo   Remove it first:  rmdir /S /Q "%LINK%"
        echo.
        pause
        exit /b 1
    )
) else (
    mklink /J "%LINK%" "%HERE%\data" >nul 2>&1
    if !errorlevel! neq 0 (
        mklink /D "%LINK%" "%HERE%\data" >nul 2>&1
        if !errorlevel! neq 0 (
            echo.
            echo   [ERROR] Could not create %LINK%.
            echo   Drive may be FAT32/exFAT. Move HermesPortable to NTFS
            echo   or enable Windows Developer Mode.
            echo.
            pause
            exit /b 1
        )
    )
)

rem -- Convert Windows path to WSL path -------------------
for /f "usebackq delims=" %%I in (`wsl wslpath "%HERE%"`) do set "WSL_HERE=%%I"
if not defined WSL_HERE (
    echo   [ERROR] Could not convert path: %HERE%
    pause
    exit /b 1
)

rem -- Pick a Linux venv directory ------------------------
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
echo.

rem -- First-run / explicit config mode -------------------
set "HAS_KEY=false"
wsl test -f "%WSL_HERE%/data/.env" 2>nul
if !errorlevel! equ 0 (
    wsl grep -qE "^[A-Z_]+_API_KEY=.{10,}" "%WSL_HERE%/data/.env" 2>nul
    if !errorlevel! equ 0 set "HAS_KEY=true"
)

rem -- Pass paths to WSL via WSLENV, not string interpolation ------------
rem  Previous versions built bash -c commands by interpolating
rem  !WSL_HERE! and !WSL_VENV! into a quoted shell string:
rem    wsl bash -c "cd '!WSL_HERE_SAFE!' && ..."
rem  Two layers of escaping had to agree (cmd's double quotes AND bash's
rem  single quotes). A literal " or \ in the path survived neither layer,
rem  so users whose HermesPortable ended up under an unusual path
rem  silently got wrong commands dispatched into WSL. WSLENV is the
rem  supported mechanism: list variable names (with /p to translate paths
rem  to Linux form automatically), set them in the cmd-side environment,
rem  and WSL reads them through its own API without any shell parsing.
rem  See: https://learn.microsoft.com/en-us/windows/wsl/filesystems#wslenv
set "HP_HERE=%HERE%"
set "HP_VENV=%WSL_VENV%"
rem  HP_HERE is a Windows path and gets the /p translation (C:\foo -> /mnt/c/foo).
rem  HP_VENV is already a Linux path (we derived it via wslpath above), so no
rem  /p — just pass it through unchanged. Same for HERMES_MODE/HERMES_BROWSER_OPENED
rem  which are plain flags.
set "WSLENV=HP_HERE/p:HP_VENV:HERMES_MODE:HERMES_BROWSER_OPENED"

if /I "%~1"=="--config" goto :run_config
if "%HAS_KEY%"=="false" goto :run_config
goto :run_hermes

:run_config
echo   Opening config panel at http://127.0.0.1:17520 ...
start "" "http://127.0.0.1:17520"
set "HERMES_MODE=config"
set "HERMES_BROWSER_OPENED=1"
rem  Inside WSL, HP_HERE and HP_VENV are already populated via WSLENV.
rem  The only strings bash receives through cmd are the literal script
rem  body below (ASCII, no variable interpolation of untrusted data)
rem  and %*. $HP_HERE / $HP_VENV resolve purely inside bash.
wsl bash -c "cd \"$HP_HERE\" && export HOME=\"$HP_HERE/_home\" HERMES_HOME=\"$HP_HERE/data\" && exec \"$HP_VENV/bin/python\" \"$HP_HERE/config_server.py\""
set "EXITCODE=%errorlevel%"
goto :done

:run_hermes
rem Best-effort webui launch. Same WSLENV mechanism; the backgrounded
rem job is detached with nohup inside bash so the outer wsl call returns.
wsl bash -c "command -v hermes-web-ui >/dev/null 2>&1 && (cd \"$HP_HERE\" && export HOME=\"$HP_HERE/_home\" PATH=\"$HP_HERE/node-linux-x64/bin:$HP_HERE/node/bin:$PATH\" HERMES_HOME=\"$HP_HERE/data\" && nohup hermes-web-ui start --port 8648 >/dev/null 2>&1 &)" 2>nul

wsl bash -c "cd \"$HP_HERE\" && export HOME=\"$HP_HERE/_home\" HERMES_HOME=\"$HP_HERE/data\" PATH=\"$HP_VENV/bin:$HP_HERE/node-linux-x64/bin:$HP_HERE/node/bin:$PATH\" && exec \"$HP_VENV/bin/hermes\" \"$@\"" -- %*
set "EXITCODE=%errorlevel%"
goto :done

:done
if not "%EXITCODE%"=="0" (
    echo.
    echo   Hermes exited with code %EXITCODE%.
    pause
)
endlocal & exit /b %EXITCODE%
