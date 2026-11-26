#!/usr/bin/env bash
# Envoltorio de bash: ejecuta verificar_targets.py con el Python del entorno de la API
# (api/.venv) si existe. Los argumentos se pasan tal cual.
# Uso, desde la raiz del repositorio:  ./monitoreo/scripts/verificar_targets.sh [opciones]
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
RAIZ="$(cd "$DIR/../.." && pwd)"
PY="$RAIZ/api/.venv/bin/python"
[ -x "$PY" ] || PY="$RAIZ/api/.venv/Scripts/python.exe"
[ -x "$PY" ] || PY="$(command -v python3 || command -v python)"
export PYTHONIOENCODING=utf-8
exec "$PY" "$DIR/verificar_targets.py" "$@"
