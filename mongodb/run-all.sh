#!/usr/bin/env bash
# =============================================================================
# run-all.sh
# -----------------------------------------------------------------------------
# Orquestador end-to-end del modulo documental del Fixture 2030.
#
# Levanta MongoDB en Docker, espera a que este saludable, y ejecuta en orden
# los seis scripts de mongosh. Al finalizar, captura la evidencia de cada
# ejecucion en el directorio evidencia/.
#
# Uso:
#   ./run-all.sh                # ejecuta todo el flujo
#   ./run-all.sh reset          # tumba contenedor + volumen y arranca desde cero
# =============================================================================
set -euo pipefail

CONTAINER=fixture2030-mongodb
MDB_USER=admin
MDB_PASS=admin
MDB_DB=fixture2030
EVID_DIR="./evidencia"

mkdir -p "$EVID_DIR"

# --- reset opcional ---------------------------------------------------------
if [[ "${1:-}" == "reset" ]]; then
  echo ">>> reset: docker compose down -v"
  docker compose down -v || true
fi

# --- levantar contenedor ----------------------------------------------------
echo ">>> Levantando MongoDB (docker compose up -d)"
docker compose up -d

# --- esperar a que este healthy --------------------------------------------
echo -n ">>> Esperando healthcheck de MongoDB "
for i in {1..30}; do
  status=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo "starting")
  if [[ "$status" == "healthy" ]]; then
    echo " OK"
    break
  fi
  echo -n "."
  sleep 2
done

if [[ "$status" != "healthy" ]]; then
  echo ""
  echo "!!! MongoDB no llego a healthy. Ver logs:"
  docker compose logs --tail=40 mongodb
  exit 1
fi

# --- helper: ejecutar un script mongosh y capturar evidencia ----------------
run_mongosh() {
  local script="$1"
  local nombre="$(basename "$script" .js)"
  local out="$EVID_DIR/${nombre}.log"
  echo ""
  echo ">>> Ejecutando $script  (salida -> $out)"
  docker exec -i "$CONTAINER" mongosh \
    -u "$MDB_USER" -p "$MDB_PASS" \
    --authenticationDatabase admin \
    --quiet \
    "$MDB_DB" --file "/scripts/$(basename "$script")" \
    | tee "$out"
}

# --- flujo completo ---------------------------------------------------------
run_mongosh scripts/01-cargar-datos.js
run_mongosh scripts/02-crear-indices.js
run_mongosh scripts/03-operaciones-crud.js
run_mongosh scripts/04-consultas.js
run_mongosh scripts/05-agregacion.js
run_mongosh scripts/06-analisis-rendimiento.js

echo ""
echo "=============================================================="
echo " Flujo completo OK. Evidencia en $EVID_DIR/"
echo " Interfaz web opcional: http://localhost:8081  (admin/admin)"
echo "=============================================================="
