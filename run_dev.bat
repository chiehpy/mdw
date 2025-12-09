@echo off
REM Activar el venv (asumiendo que ya existe)
call venv\Scripts\activate

REM Levantar el servidor en modo desarrollo
uvicorn app.main:app --reload --port 8000
