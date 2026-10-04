#!/usr/bin/env bash
# =============================================================================
# Hito 6 - Comentarios masivos del Fixture 2030 (Grupo 8)
# ejecutar_todo.sh : ejecuta esquema -> muestra -> CRUD -> consultas y guarda la
# salida de cada paso en docs/evidencia/logs/ (RF13, RNF3, RNF9).
# La carga masiva y la medicion se ejecutan aparte con scripts/carga_o_prueba.sh.
#
# Uso (desde la carpeta cassandra/, con 'docker compose up -d' ya ejecutado):
#   bash scripts/ejecutar_todo.sh
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1

CONTENEDOR="${CONTENEDOR:-fixture2030-cassandra}"
LOGS="docs/evidencia/logs"
mkdir -p "$LOGS"

echo "Esperando a que Cassandra acepte conexiones CQL (el primer inicio puede tardar)..."
for i in $(seq 1 40); do
  if docker exec "$CONTENEDOR" cqlsh -e "DESCRIBE KEYSPACES" >/dev/null 2>&1; then break; fi
  [ "$i" -eq 40 ] && { echo "Cassandra no respondio. Revisar: docker compose logs cassandra"; exit 1; }
  sleep 10
done

{
  echo "Fecha de ejecucion (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  docker exec "$CONTENEDOR" nodetool status
} 2>&1 | tee "$LOGS/00_estado_nodo.log"

paso() {  # paso <numero_nombre> <archivo.cql>
  echo "=== $2 ($(date -u +%H:%M:%SZ)) ==="
  docker exec -i "$CONTENEDOR" cqlsh -f "/scripts/$2" 2>&1 | tee "$LOGS/$1.log"
}
paso 01_esquema      esquema.cql
paso 02_carga_muestra carga_muestra.cql
paso 03_crud         crud.cql
paso 04_consultas    consultas.cql

echo
echo "Listo. Registros en $LOGS/"
