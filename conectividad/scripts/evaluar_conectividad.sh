#!/usr/bin/env bash
# Hito 11 - Evaluacion de conectividad (Linux / macOS / Git Bash).
# Usa el Python del entorno virtual de la API (api/.venv), con los mismos
# drivers que la API del Hito 10. Si no existe, usa python3 y las pruebas con
# driver quedan en SKIP.
#
# Ejemplos (desde la carpeta conectividad/):
#   ./scripts/evaluar_conectividad.sh --modo completo --iniciar-api --etiqueta final
#   ./scripts/evaluar_conectividad.sh --modo tcp --producto redis,neo4j
#   ./scripts/evaluar_conectividad.sh falla          # fallas controladas
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
PY=python3
for c in "$DIR/../../api/.venv/bin/python" "$DIR/../../api/.venv/Scripts/python.exe"; do
  [ -x "$c" ] && PY="$c" && break
done
export PYTHONIOENCODING=utf-8
if [ "${1:-}" = "falla" ]; then
  shift
  exec "$PY" "$DIR/falla_controlada.py" "$@"
fi
exec "$PY" "$DIR/evaluar_conectividad.py" "$@"
