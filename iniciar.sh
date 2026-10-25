#!/usr/bin/env sh
# Abre el Resumidor. La primera vez crea el entorno e instala lo necesario.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Preparando el entorno por primera vez..."
  python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt || exit 1
fi
exec .venv/bin/python -m resumidor --web
