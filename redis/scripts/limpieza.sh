#!/bin/sh
# =============================================================================
# limpieza.sh - Hito 7 (Grupo 8) - paso OPCIONAL
# Borra claves por prefijo, recorriendo con SCAN y eliminando con DEL.
# No se usa FLUSHALL ni KEYS *: solo se tocan los prefijos indicados (RNF8).
#
# Uso (dentro del contenedor):
#   sh /scripts/limpieza.sh prueba:        # solo claves de prueba (las del hito)
#   sh /scripts/limpieza.sh todo           # prueba:, sesion:, cache:, partido:, encuesta:
# Para repoblar despues: sh /scripts/ejecutar_bloques.sh /scripts/carga_muestra.redis carga
#
# Para empezar de cero incluso en disco: docker compose down y borrar a mano
# ~/docker/data/redis (solo con esa intencion explicita).
# =============================================================================
. "$(dirname "$0")/lib_redis.sh"

if [ -z "$1" ]; then
  echo "Uso: sh limpieza.sh <prefijo> | todo" >&2
  exit 1
fi

if [ "$1" = "todo" ]; then
  prefijos="prueba: sesion: cache: partido: encuesta:"
else
  prefijos="$1"
fi

for p in $prefijos; do
  n=$(borrar_prefijo "$p")
  echo "Prefijo $p : $n clave(s) borrada(s)"
done
