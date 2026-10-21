#!/usr/bin/env bash
# Inicia la API localmente (Linux/macOS/Git Bash). Requiere el entorno creado
# (ver README). Lee la configuracion de .env si existe.
set -e
cd "$(dirname "$0")/.."
[ -f .env ] && export $(grep -v '^#' .env | xargs) || true
exec python -m uvicorn app.main:app --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8000}" --reload
