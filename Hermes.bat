@echo off
setlocal enabledelayedexpansion
set "HERE=%~dp0"
set "HERMES_HOME=%HERE%data"
set "PATH=%HERE%venv\Scripts;%HERE%python;%PATH%"

echo.
echo   ╦ ╦╔═╗╦═╗╔═╗╔═╗╔═╗╔╦╗╔═╗
echo   ╠═╣╠═╣╠╦╝╠═╝║╣ ║   ║ ║ ║
echo   ╩ ╩╩ ╩╩╚═╩  ╚═╝╚═╝╩ ╩╚═╝  Portable
echo.

REM Check if API key is configured
set "HAS_KEY=false"
if exist "%HERE%data\.env" (
    findstr /R "^[A-Z_]*_API_KEY=sk-" "%HERE%data\.env" >nul 2>&1
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

"%HERE%venv\Scripts\hermes.exe" %*
