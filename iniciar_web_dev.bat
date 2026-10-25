@echo off
title Audio Dubbing Studio (Modo Desarrollo con HMR)
color 0a
echo ========================================================
echo    Modo Desarrollo (FastAPI :8000 + Vite :5173 HMR)
echo ========================================================
echo.

:: 1. Iniciar FastAPI en segundo plano
start "Backend FastAPI" /b python -m uvicorn backend.server:app --host 127.0.0.1 --port 8000 --reload

:: 2. Iniciar Vite y abrir navegador
cd frontend
start http://localhost:5173
npm run dev
