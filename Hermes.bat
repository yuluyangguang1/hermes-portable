@echo off
setlocal enabledelayedexpansion
set "HERE=%~dp0"

REM ── Multi-platform package detection ──
if exist "%HERE%venv-windows-x64\Scripts\hermes.exe" (
    set "VENV_DIR=%HERE%venv-windows-x64"
    set "PYTHON_DIR=%HERE%python-windows-x64"
) else if exist "%HERE%venv\Scripts\hermes.exe" (
    set "VENV_DIR=%HERE%venv"
    set "PYTHON_DIR=%HERE%python"
) else (
    echo.
    echo   [ERROR] 未找到 venv 目录
    echo   请先运行构建脚本: python build_windows.py
    echo.
    pause
    exit /b 1
)

set "HERMES_HOME=%HERE%data"
set "PATH=%VENV_DIR%\Scripts;%HERE%node;%PYTHON_DIR%;%PATH%"

echo.
echo   ╦ ╦╔═╗╦═╗╔═╗╔═╗╔═╗╔╦╗╔═╗
echo   ╠═╣╠═╣╠╦╝╠═╝║╣ ║   ║ ║ ║
echo   ╩ ╩╩ ╩╩╚═╩  ╚═╝╚═╝╩ ╩╚═╝  Portable
echo.

REM Check if API key is configured
set "HAS_KEY=false"
if exist "%HERE%data\.env" (
    findstr /R "^[A-Z_]*_API_KEY=." "%HERE%data\.env" >nul 2>&1
    if !errorlevel! equ 0 set "HAS_KEY=true"
)

if "%HAS_KEY%"=="false" (
    echo   首次使用！正在打开配置面板...
    echo   请在浏览器中完成 API Key 配置。
    echo.
    start "" "http://127.0.0.1:17520"
    "%VENV_DIR%\Scripts\python.exe" "%HERE%config_server.py"
    goto :eof
)

if "%1"=="--config" (
    start "" "http://127.0.0.1:17520"
    "%VENV_DIR%\Scripts\python.exe" "%HERE%config_server.py"
    goto :eof
)

REM Start hermes-web-ui in background (if installed)
set "WEBUI_OK=false"
where hermes-web-ui >nul 2>&1
if !errorlevel! equ 0 (
    start /b hermes-web-ui start --port 8648 >nul 2>&1
    set "WEBUI_OK=true"
)

"%VENV_DIR%\Scripts\hermes.exe" %*
