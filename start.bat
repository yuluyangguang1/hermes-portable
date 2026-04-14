@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PORTABLE_DIR=%SCRIPT_DIR%portable"
set "DATA_DIR=%SCRIPT_DIR%data"
set "VENV_DIR=%PORTABLE_DIR%\venv"

:: Check if setup has been run
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo ERROR: Hermes Portable is not set up yet!
    echo Please run setup.bat first.
    pause
    exit /b 1
)

:: Set HERMES_HOME to point to our data directory
set "HERMES_HOME=%DATA_DIR%"
set "PATH=%VENV_DIR%\Scripts;%PORTABLE_DIR%\python;%PATH%"

:: Title
echo.
echo  ╦ ╦╔═╗╦═╗╔═╗╔═╗╔═╗╔╦╗╔═╗
echo  ╠═╣╠═╣╠╦╝╠═╝║╣ ║   ║ ║ ║
echo  ╩ ╩╩ ╩╩╚═╩  ╚═╝╚═╝╩ ╩╚═╝  Portable
echo.

:: Launch Hermes
cd /d "%SCRIPT_DIR%"
"%VENV_DIR%\Scripts\hermes.exe" %*

:: Keep window open if there was an error
if !errorlevel! neq 0 (
    echo.
    echo Hermes exited with error code !errorlevel!
    pause
)
