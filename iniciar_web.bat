@echo off
title Audio Dubbing Studio (React + FastAPI)
color 0b
echo ========================================================
echo    Audio Dubbing Studio - Interfaz Web de Alto Rendimiento
echo ========================================================
echo.
echo Iniciando servidor local en http://127.0.0.1:8000 ...
echo Abriendo tu navegador predeterminado...
echo.

:: Abrir navegador tras 1.5 segundos en segundo plano
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8000"

:: Iniciar servidor FastAPI (sirve la API y la app React)
python -m uvicorn backend.server:app --host 127.0.0.1 --port 8000

pause

