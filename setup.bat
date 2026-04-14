@echo off
setlocal enabledelayedexpansion

echo ========================================
echo   Hermes Portable - Windows Setup
echo ========================================
echo.

set "PORTABLE_DIR=%~dp0portable"
set "DATA_DIR=%~dp0data"
set "UV_PATH=%PORTABLE_DIR%\uv.exe"

:: Create directories
if not exist "%PORTABLE_DIR%" mkdir "%PORTABLE_DIR%"
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
if not exist "%DATA_DIR%\sessions" mkdir "%DATA_DIR%\sessions"
if not exist "%DATA_DIR%\skills" mkdir "%DATA_DIR%\skills"
if not exist "%DATA_DIR%\logs" mkdir "%DATA_DIR%\logs"
if not exist "%DATA_DIR%\memories" mkdir "%DATA_DIR%\memories"
if not exist "%DATA_DIR%\cron" mkdir "%DATA_DIR%\cron"

:: Step 1: Download uv
echo [1/5] Downloading uv package manager...
if not exist "%UV_PATH%" (
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.exe' -OutFile '%UV_PATH%'"
    if !errorlevel! neq 0 (
        echo ERROR: Failed to download uv
        pause
        exit /b 1
    )
    echo uv downloaded successfully.
) else (
    echo uv already exists, skipping.
)

:: Step 2: Install Python
echo.
echo [2/5] Installing portable Python...
set "PYTHON_DIR=%PORTABLE_DIR%\python"
set "UV_PYTHON_INSTALL_DIR=%PYTHON_DIR%"
"%UV_PATH%" python install 3.12 --install-dir "%PYTHON_DIR%"
if !errorlevel! neq 0 (
    echo ERROR: Failed to install Python
    pause
    exit /b 1
)
echo Python installed successfully.

:: Step 3: Clone hermes-agent
echo.
echo [3/5] Downloading hermes-agent...
set "HERMES_SRC=%PORTABLE_DIR%\hermes-agent"
if not exist "%HERMES_SRC%" (
    git clone --depth 1 https://github.com/NousResearch/hermes-agent.git "%HERMES_SRC%"
    if !errorlevel! neq 0 (
        echo ERROR: Failed to clone hermes-agent
        echo Please install git: https://git-scm.com/download/win
        pause
        exit /b 1
    )
    echo hermes-agent cloned successfully.
) else (
    echo hermes-agent already exists, updating...
    cd /d "%HERMES_SRC%"
    git pull --ff-only 2>nul
    echo hermes-agent updated.
)

:: Step 4: Create virtual environment and install dependencies
echo.
echo [4/5] Creating virtual environment and installing dependencies...
set "VENV_DIR=%PORTABLE_DIR%\venv"
"%UV_PATH%" venv "%VENV_DIR%" --python "%PYTHON_DIR%\python3.12.exe"
if !errorlevel! neq 0 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)

"%UV_PATH%" pip install -e "%HERMES_SRC%[all]" --python "%VENV_DIR%\Scripts\python.exe"
if !errorlevel! neq 0 (
    echo WARNING: 'all' extras failed, trying core dependencies only...
    "%UV_PATH%" pip install -e "%HERMES_SRC%[cron,messaging,cli,mcp]" --python "%VENV_DIR%\Scripts\python.exe"
    if !errorlevel! neq 0 (
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
)
echo Dependencies installed successfully.

:: Step 5: Create default config
echo.
echo [5/5] Setting up configuration...
if not exist "%DATA_DIR%\.env" (
    (
        echo # Hermes Portable - Environment Variables
        echo # Add your API keys here
        echo.
        echo # OPENROUTER_API_KEY=your_key_here
        echo # ANTHROPIC_API_KEY=your_key_here
        echo # OPENAI_API_KEY=your_key_here
    ) > "%DATA_DIR%\.env"
    echo Created default .env file.
)

if not exist "%DATA_DIR%\config.yaml" (
    (
        echo # Hermes Portable Configuration
        echo model:
        echo   default: "openrouter/anthropic/claude-sonnet-4"
        echo   provider: "openrouter"
        echo.
        echo terminal:
        echo   backend: "local"
        echo   timeout: 180
        echo.
        echo compression:
        echo   enabled: true
        echo   threshold: 0.50
        echo   target_ratio: 0.20
        echo.
        echo display:
        echo   skin: "default"
        echo   tool_progress: true
        echo   show_cost: true
    ) > "%DATA_DIR%\config.yaml"
    echo Created default config.yaml.
)

echo.
echo ========================================
echo   Setup Complete! 
echo ========================================
echo.
echo Next steps:
echo 1. Edit data\.env to add your API keys
echo 2. Run start.bat to launch Hermes
echo.
pause
