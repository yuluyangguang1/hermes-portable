@echo off
setlocal enabledelayedexpansion
set "HERE=%~dp0"
set "HERMES_HOME=%HERE%data"
set "PATH=%HERE%venv\Scripts;%HERE%node;%HERE%python;%PATH%"

echo.
echo   ╦ ╦╔═╗╦═╗╔═╗╔═╗╔═╗╔╦╗╔═╗
echo   ╠═╣╠═╣╠╦╝╠═╝║╣ ║   ║ ║ ║
echo   ╩ ╩╩ ╩╩╚═╩  ╚═╝╚═╝╩ ╩╚═╝  Portable
echo.

REM Check if native venv exists
if not exist "%HERE%venv\Scripts\hermes.exe" (
    echo   [ERROR] 未找到 venv\Scripts\hermes.exe
    echo.
    echo   请先运行构建脚本生成完整环境：
    echo     python build_windows.py
    echo.
    echo   或者使用 WSL2 模式：双击 Hermes-WSL.bat
    echo.
    pause
    exit /b 1
)

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
    "%HERE%venv\Scripts\python.exe" "%HERE%config_server.py"
    goto :eof
)

if "%1"=="--config" (
    start "" "http://127.0.0.1:17520"
    "%HERE%venv\Scripts\python.exe" "%HERE%config_server.py"
    goto :eof
)

REM Start hermes-web-ui in background (if installed)
set "WEBUI_OK=false"
where hermes-web-ui >nul 2>&1
if !errorlevel! equ 0 (
    start /b hermes-web-ui start --port 8648 >nul 2>&1
    set "WEBUI_OK=true"
)

"%HERE%venv\Scripts\hermes.exe" %*
