#!/usr/bin/env bash
# =============================================================================
# Hito 6 - Comentarios masivos del Fixture 2030 (Grupo 8)
# carga_o_prueba.sh : carga masiva (1.100.000 comentarios, > 1.000.000) + medicion de
#                     escrituras (RF11, RF12, RF13, RNF9)
#
# Metodo de medicion: COPY ... FROM de cqlsh, ejecutado dentro del contenedor.
# Se mide el tiempo de pared de cada COPY y se informa la tasa (filas/s).
# Cada fila del CSV se escribe en UNA tabla; como el modelo duplica cada
# comentario en dos tablas, la cantidad de escrituras fisicas es el doble.
#
# Uso (desde la carpeta cassandra/, con el contenedor en marcha y el esquema creado):
#   bash scripts/carga_o_prueba.sh
#   TOTAL=20000 bash scripts/carga_o_prueba.sh            # prueba rapida del flujo
#   NUMPROCESSES=4 bash scripts/carga_o_prueba.sh         # variar paralelismo de COPY
#
# Idempotente (RNF7): los comentario_id del CSV son deterministas, por lo que repetir
# la carga sobrescribe las mismas filas. Para MEDIR registrar solo la PRIMERA
# corrida sobre tablas vacias (las siguientes sobrescriben datos existentes).
#
# Deja el registro en docs/evidencia/logs/carga_<fecha>.log
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1   # evita que Git Bash (Windows) reescriba rutas como /data/...

CONTENEDOR="${CONTENEDOR:-fixture2030-cassandra}"
TOTAL="${TOTAL:-1100000}"
NUMPROCESSES="${NUMPROCESSES:-2}"
CHUNKSIZE="${CHUNKSIZE:-1000}"
KS="fixture2030_comentarios"
PY="$(command -v python3 || command -v python)"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
LOG="docs/evidencia/logs/carga_${STAMP}.log"
mkdir -p docs/evidencia/logs data/generado

ahora() { "$PY" -c 'import time; print(time.time())'; }
cqlsh_e() { docker exec -i "$CONTENEDOR" cqlsh -e "$1"; }

# 1. Generar los CSV si no existen (reproducible: semilla fija)
if [ ! -f data/generado/comentarios_por_partido.csv ] || [ ! -f data/generado/comentarios_por_usuario.csv ]; then
  "$PY" scripts/generar_datos.py --total "$TOTAL"
fi
FILAS=$(( $(wc -l < data/generado/comentarios_por_partido.csv) - 1 ))

{
echo "=== PRUEBA DE CARGA - HITO 6 (Cassandra) ==="
echo "Fecha de ejecucion (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Host: $(uname -srm)"
echo "Recursos visibles para Docker: $(docker info --format '{{.NCPU}} CPUs, {{.MemTotal}} bytes de memoria')"
echo "Contenedor: $CONTENEDOR"
echo "--- Version de Cassandra (SHOW VERSION) ---"
cqlsh_e "SHOW VERSION"
echo "--- Estado del nodo (nodetool status) ---"
docker exec "$CONTENEDOR" nodetool status
echo "--- Parametros ---"
echo "Filas por CSV: $FILAS | NUMPROCESSES=$NUMPROCESSES | CHUNKSIZE=$CHUNKSIZE"

echo
echo "--- COPY 1/2: comentarios_por_partido ---"
T0=$(ahora)
cqlsh_e "COPY ${KS}.comentarios_por_partido (partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes) FROM '/data/generado/comentarios_por_partido.csv' WITH HEADER = TRUE AND NUMPROCESSES = ${NUMPROCESSES} AND CHUNKSIZE = ${CHUNKSIZE};"
T1=$(ahora)

echo
echo "--- COPY 2/2: comentarios_por_usuario ---"
cqlsh_e "COPY ${KS}.comentarios_por_usuario (usuario_id, creado_en, comentario_id, partido_id, ventana, contenido, estado) FROM '/data/generado/comentarios_por_usuario.csv' WITH HEADER = TRUE AND NUMPROCESSES = ${NUMPROCESSES} AND CHUNKSIZE = ${CHUNKSIZE};"
T2=$(ahora)

echo
echo "--- RESULTADO DE LA MEDICION ---"
"$PY" - "$FILAS" "$T0" "$T1" "$T2" <<'EOF'
import sys
filas, t0, t1, t2 = int(sys.argv[1]), *map(float, sys.argv[2:5])
d1, d2 = t1 - t0, t2 - t1
print(f"comentarios_por_partido : {filas} filas en {d1:8.1f} s -> {filas/d1:10.0f} filas/s")
print(f"comentarios_por_usuario : {filas} filas en {d2:8.1f} s -> {filas/d2:10.0f} filas/s")
print(f"Total                   : {2*filas} escrituras fisicas en {d1+d2:8.1f} s -> {2*filas/(d1+d2):10.0f} escrituras/s")
print("Objetivo del hito: 10.000 escrituras/s o mas (si el hardware lo permite).")
EOF

echo
echo "--- VERIFICACION DE LA CARGA (conteo esperado segun el CSV vs. conteo en Cassandra) ---"
ESP1=$(grep -c '^F2030-063,2030-06-22 20:35:00' data/generado/comentarios_por_partido.csv || true)
OBS1=$(cqlsh_e "SELECT COUNT(*) FROM ${KS}.comentarios_por_partido WHERE partido_id='F2030-063' AND ventana='2030-06-22 20:35:00+0000';" | awk 'NR==4{print $1}')
echo "Particion (F2030-063, ventana 20:35): esperado=$ESP1 observado=$OBS1"
ESP2=$(grep -c '^U000001,' data/generado/comentarios_por_usuario.csv || true)
OBS2=$(cqlsh_e "SELECT COUNT(*) FROM ${KS}.comentarios_por_usuario WHERE usuario_id='U000001';" | awk 'NR==4{print $1}')
echo "Particion (usuario U000001)         : esperado=$ESP2 observado=$OBS2"
echo "(Si la carga de muestra tambien esta cargada, estas dos particiones no se ven afectadas.)"
} 2>&1 | tee "$LOG"

echo "Registro guardado en $LOG"
