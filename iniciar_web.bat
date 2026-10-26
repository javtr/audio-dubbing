@echo off
title Audio Dubbing Studio (React + FastAPI)
color 0b
echo ========================================================
echo    Audio Dubbing Studio - Aplicacion Web Unificada
echo ========================================================
echo.

cd /d "%~dp0"

:: 1. Limpiar procesos huerfanos previos en puertos 8000 y 5173
echo [1/3] Verificando puertos locales...
powershell -Command "Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue).OwningProcess -Force -ErrorAction SilentlyContinue" >nul 2>&1
powershell -Command "Stop-Process -Id (Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue).OwningProcess -Force -ErrorAction SilentlyContinue" >nul 2>&1

:: 2. Iniciar servidor Backend FastAPI (puerto 8000 con auto-recarga)
echo [2/3] Iniciando backend FastAPI (puerto 8000 con auto-recarga)...
start "Backend FastAPI" /b python -m uvicorn backend.server:app --host 127.0.0.1 --port 8000 --reload

:: Esperar 2 segundos para asegurar inicio del backend
timeout /t 2 /nobreak >nul

:: 3. Abrir navegador en http://localhost:5173 e iniciar Frontend Vite
echo [3/3] Iniciando frontend y abriendo navegador en http://localhost:5173 ...
start http://localhost:5173

cd frontend
call npm run dev
