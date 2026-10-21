#!/usr/bin/env bash
# Consulta /salud y muestra que fuentes estan disponibles (RF17, RNF11).
set -e
BASE="${1:-http://localhost:8000}"
echo "Consultando $BASE/salud ..."
curl -s "$BASE/salud" | python -m json.tool
