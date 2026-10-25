@echo off
rem Doble clic para abrir el Resumidor. La primera vez crea el entorno e instala lo necesario.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Preparando el entorno por primera vez...
  python -m venv .venv || (echo Necesitas Python 3.10 o superior: https://www.python.org/downloads/ & pause & exit /b 1)
  .venv\Scripts\python -m pip install -r requirements.txt
)
.venv\Scripts\python -m resumidor --web
pause
