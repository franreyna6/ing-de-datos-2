#!/bin/sh
# =============================================================================
# lib_redis.sh - funciones comunes de los scripts .sh del Hito 7 (Grupo 8).
# Se incluye con:  . "$(dirname "$0")/lib_redis.sh"
# Corre DENTRO del contenedor: usa solo sh, redis-cli y utilidades basicas.
# =============================================================================

# valor_info <campo> : valor de un campo de INFO (por ejemplo keyspace_hits)
valor_info() {
  redis-cli INFO | tr -d '\r' | grep "^$1:" | cut -d: -f2
}

# listar_claves <patron> : claves que coinciden, una por linea, recorridas con SCAN
# (por cursor, en lotes). Nunca se usa KEYS * (RNF8). SCAN puede repetir claves:
# quien cuente debe aplicar sort -u.
listar_claves() {
  _cursor=0
  while :; do
    _salida=$(redis-cli SCAN "$_cursor" MATCH "$1" COUNT 200)
    _cursor=$(printf '%s\n' "$_salida" | head -n 1)
    printf '%s\n' "$_salida" | tail -n +2
    [ "$_cursor" = "0" ] && break
  done
}

# borrar_prefijo <prefijo> : borra con DEL las claves que empiezan con el prefijo.
# Devuelve (por stdout) la cantidad borrada.
borrar_prefijo() {
  _n=0
  for _k in $(listar_claves "$1*" | sort -u); do
    redis-cli DEL "$_k" > /dev/null
    _n=$((_n + 1))
  done
  echo "$_n"
}

# ahora_ms : milisegundos desde la epoca
ahora_ms() {
  echo $(( $(date +%s%N) / 1000000 ))
}
