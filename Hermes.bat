@echo off
setlocal
set "HERE=%~dp0"

REM Check WSL availability
wsl --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  ╔═══════════════════════════════════════╗
    echo  ║  Hermes Portable 需要 WSL2 才能运行   ║
    echo  ╚═══════════════════════════════════════╝
    echo.
    echo  请先安装 WSL2 (Windows Subsystem for Linux):
    echo.
    echo    1. 以管理员身份打开 PowerShell
    echo    2. 运行: wsl --install
    echo    3. 重启电脑
    echo    4. 详情: https://learn.microsoft.com/windows/wsl/install
    echo.
    pause
    exit /b 1
)

REM Convert Windows path to WSL path
for /f "usebackq delims=" %%I in (`wsl wslpath "%HERE:.=\\%"`) do set WSL_HERE=%%I

echo.
echo   ╦ ╦╔═╗╦═╗╔═╗╔═╗╔═╗╔╦╗╔═╗
echo   ╠═╣╠═╣╠╦╝╠═╝║╣ ║   ║ ║ ║
echo   ╩ ╩╩ ╩╩╚═╩  ╚═╝╚═╝╩ ╩╚═╝  Portable
echo.
echo   Running via WSL2...
echo.

REM Check if API key is configured
wsl test -f "%WSL_HERE%/data/.env" ^&^& wsl grep -qE "^[A-Z_]+_API_KEY=" "%WSL_HERE%/data/.env"
if %errorlevel% neq 0 (
    echo   首次使用！正在打开配置面板...
    echo   请在浏览器中完成 API Key 配置。
    echo.
    start http://127.0.0.1:17520
    wsl bash -c "cd '%WSL_HERE%' && export HERMES_HOME='%WSL_HERE%/data' && '%WSL_HERE%/venv/bin/python' '%WSL_HERE%/config_server.py'"
    goto :eof
)

if "%1"=="--config" (
    start http://127.0.0.1:17520
    wsl bash -c "cd '%WSL_HERE%' && export HERMES_HOME='%WSL_HERE%/data' && '%WSL_HERE%/venv/bin/python' '%WSL_HERE%/config_server.py'"
    goto :eof
)

wsl bash -c "cd '%WSL_HERE%' && export HERMES_HOME='%WSL_HERE%/data' && '%WSL_HERE%/venv/bin/hermes' %*"
