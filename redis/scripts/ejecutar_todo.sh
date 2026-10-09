#!/usr/bin/env bash
# =============================================================================
# Hito 7 - Cache de usuarios y sesiones del Fixture 2030 (Grupo 8)
# ejecutar_todo.sh : corre TODOS los scripts del modulo contra el contenedor y
# guarda la salida de cada paso en docs/evidencia/logs/ (RF13, RNF3, RNF10).
#
# Uso (desde la carpeta redis/, con 'docker compose up -d' ya ejecutado):
#   bash scripts/ejecutar_todo.sh
#   SIN_PRESION=1 bash scripts/ejecutar_todo.sh     # omite la prueba de presion de memoria
#
# La prueba de presion de memoria baja maxmemory temporalmente y evicta claves;
# al terminar restaura la configuracion y recarga la muestra (idempotente).
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1                # Git Bash (Windows): no convertir rutas /scripts/...

CONTENEDOR="${CONTENEDOR:-fixture2030-redis}"
LOGS="docs/evidencia/logs"
mkdir -p "$LOGS"
fallos=0

echo "Esperando a que Redis responda PONG..."
listo=0
for i in $(seq 1 30); do
  if [ "$(docker exec "$CONTENEDOR" redis-cli PING 2>/dev/null | tr -d '\r')" = "PONG" ]; then listo=1; break; fi
  sleep 2
done
[ "$listo" -eq 1 ] || { echo "Redis no respondio. Revisar: docker compose ps / docker compose logs redis"; exit 1; }

# ---- 00. Ambiente (RF1, RNF1, RNF10): fecha, version observada de latest y recursos ----
{
  echo "Fecha de ejecucion (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "Equipo (uname): $(uname -sr 2>/dev/null || echo desconocido)"
  docker compose version 2>&1 | head -1
  docker info --format 'Docker: {{.ServerVersion}} | CPUs: {{.NCPU}} | Memoria total (bytes): {{.MemTotal}} | SO: {{.OperatingSystem}}' 2>&1
  docker image inspect redis:latest --format 'Imagen redis:latest: id {{.Id}} | creada {{.Created}}' 2>&1
  echo "Servidor: $(docker exec "$CONTENEDOR" redis-server --version | tr -d '\r')"
  echo "Cliente:  $(docker exec "$CONTENEDOR" redis-cli --version | tr -d '\r')"
  echo
  docker compose ps 2>&1
} 2>&1 | tee "$LOGS/00_ambiente.log"

paso() {  # paso <nombre_del_log> <comando dentro del contenedor...>
  nombre="$1"; shift
  echo "=== $nombre ($(date -u +%H:%M:%SZ)) ==="
  if ! docker exec "$CONTENEDOR" "$@" 2>&1 | tr -d '\r' | tee "$LOGS/$nombre.log"; then fallos=$((fallos + 1)); fi
}

paso 01_inicializacion          sh /scripts/ejecutar_bloques.sh /scripts/inicializacion.redis
paso 02_carga_muestra           sh /scripts/ejecutar_bloques.sh /scripts/carga_muestra.redis carga
paso 03_sesiones                sh /scripts/ejecutar_bloques.sh /scripts/sesiones.redis
paso 04_cache                   sh /scripts/ejecutar_bloques.sh /scripts/cache.redis

# Servidor no disponible (simulado): un cliente apuntando a un puerto sin Redis (RF7)
{
  echo
  echo "# --- 7. Servidor no disponible (simulado) ---"
  echo "# Un cliente que apunta a un puerto sin Redis recibe un error de conexion. Comportamiento"
  echo "# esperado de la aplicacion: responder consultando la fuente de verdad (modo degradado)."
  echo "> redis-cli -p 6399 PING"
  docker exec "$CONTENEDOR" redis-cli -p 6399 PING 2>&1 | tr -d '\r' | sed 's/^/  /'
} | tee -a "$LOGS/04_cache.log"

paso 05_concurrencia_comandos   sh /scripts/ejecutar_bloques.sh /scripts/concurrencia.redis
paso 06_concurrencia_paralela   sh /scripts/concurrencia_paralela.sh
paso 07_auditoria_ttl           sh /scripts/auditoria_ttl.sh
paso 08_metricas                sh /scripts/ejecutar_bloques.sh /scripts/metricas.redis
paso 09_medicion                sh /scripts/medicion.sh
if [ -z "${SIN_PRESION:-}" ]; then
  paso 10_presion_memoria       sh /scripts/presion_memoria.sh
  paso 11_metricas_final        sh /scripts/ejecutar_bloques.sh /scripts/metricas.redis
fi

# ---- 12. Persistencia (RNF2): los datos y los TTL sobreviven al reinicio del contenedor ----
{
  echo "=== ANTES del reinicio ($(date -u +%H:%M:%SZ)) ==="
  docker exec "$CONTENEDOR" sh /scripts/ejecutar_bloques.sh /scripts/persistencia.redis 2>&1 | tr -d '\r'
  echo
  echo "=== docker compose restart redis ==="
  docker compose restart redis 2>&1
  back=0
  for i in $(seq 1 30); do
    if [ "$(docker exec "$CONTENEDOR" redis-cli PING 2>/dev/null | tr -d '\r')" = "PONG" ]; then back=1; break; fi
    sleep 2
  done
  echo "Redis volvio a responder: $([ "$back" -eq 1 ] && echo si || echo NO)"
  echo
  echo "=== DESPUES del reinicio ($(date -u +%H:%M:%SZ)) ==="
  docker exec "$CONTENEDOR" sh /scripts/ejecutar_bloques.sh /scripts/persistencia.redis 2>&1 | tr -d '\r'
} 2>&1 | tee "$LOGS/12_persistencia.log"

echo
if [ "$fallos" -eq 0 ]; then
  echo "Listo. Registros en $LOGS/ (sin pasos fallidos)."
else
  echo "Listo con $fallos paso(s) que devolvieron error. Revisar los logs en $LOGS/."
fi
