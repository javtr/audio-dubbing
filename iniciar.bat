@echo off
title Audio Dubbing Studio
cd /d "%~dp0"
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================================
    echo [ERROR] La aplicacion se cerro de forma inesperada.
    echo ========================================================
    pause
)

