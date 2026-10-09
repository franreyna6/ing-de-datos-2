#!/bin/sh
# =============================================================================
# presion_memoria.sh - Hito 7 (Grupo 8)
# Demuestra que EXPIRACION (TTL) y EVICCION (maxmemory) son cosas distintas y que
# efecto tiene la politica configurada sobre sesiones y cache (RF10, RF13).
# Corre dentro del contenedor. ES DESTRUCTIVO PARA LA MUESTRA: al terminar se
# restauran maxmemory y la politica, se borran las claves de prueba y se vuelve
# a cargar carga_muestra.redis (que es idempotente).
#
# Pasos
#   1. Se baja maxmemory a (memoria usada + 3 MB) con CONFIG SET.
#   2. Con la politica del Compose (volatile-lru) se escriben 6000 claves de ~1 KB
#      con TTL de 600 s. Se espera que Redis evicte claves CON TTL (entre ellas,
#      sesiones y cache aun vigentes: se cuentan antes y despues) y que NO falle
#      ninguna escritura.
#   3. Se cambia a noeviction y se escribe otro lote: al llegar al limite Redis
#      rechaza las escrituras con error OOM y no elimina nada.
#   4. Se restauran maxmemory y la politica, se limpian las pruebas y se recarga la muestra.
#
# Uso: sh /scripts/presion_memoria.sh
# =============================================================================
. "$(dirname "$0")/lib_redis.sh"
AQUI="$(dirname "$0")"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

lote() {  # lote <prefijo> <cantidad> : comandos SET de ~1 KB con TTL de 600 s
  awk -v p="$1" -v n="$2" 'BEGIN{ v=sprintf("%1000s",""); gsub(/ /,"x",v); for(i=1;i<=n;i++) printf "SET %s:%d %s EX 600\n", p, i, v }'
}
contar() { grep -c "$1" "$2" 2>/dev/null || true; }

echo "Fecha de ejecucion (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Redis (version observada): $(valor_info redis_version)"
echo

politica_original=$(valor_info maxmemory_policy)
limite_original=$(valor_info maxmemory)
usada=$(valor_info used_memory)
limite=$((usada + 3 * 1024 * 1024))
sesiones_antes=$(listar_claves "sesion:*" | sort -u | wc -l | tr -d ' ')
cache_antes=$(listar_claves "cache:*" | sort -u | wc -l | tr -d ' ')
evict_antes=$(valor_info evicted_keys)

echo "=== Estado inicial ==="
echo "maxmemory original: $limite_original bytes | politica original: $politica_original"
echo "Memoria usada: $usada bytes | sesiones: $sesiones_antes | claves de cache: $cache_antes | evicted_keys: $evict_antes"
echo
echo "=== 1. Se baja maxmemory a (usada + 3 MB) = $limite bytes ==="
redis-cli CONFIG SET maxmemory "$limite"

echo
echo "=== 2. Politica $politica_original: se escriben 6000 claves de ~1 KB con TTL ==="
lote "prueba:presion" 6000 | redis-cli > "$TMP/r1.txt" 2>&1
ok1=$(contar '^OK' "$TMP/r1.txt"); oom1=$(contar '^OOM' "$TMP/r1.txt")
sesiones_despues=$(listar_claves "sesion:*" | sort -u | wc -l | tr -d ' ')
cache_despues=$(listar_claves "cache:*" | sort -u | wc -l | tr -d ' ')
evict_despues=$(valor_info evicted_keys)
echo "Escrituras OK: $ok1 | rechazadas por OOM: $oom1"
echo "evicted_keys: $evict_antes -> $evict_despues (evicciones de esta prueba: $((evict_despues - evict_antes)))"
echo "Sesiones vigentes: $sesiones_antes -> $sesiones_despues"
echo "Claves de cache:   $cache_antes -> $cache_despues"
echo "Memoria usada ahora: $(valor_info used_memory_human) (limite $(valor_info maxmemory_human))"
echo "Lectura: ninguna clave vencio por TTL (todas tenian cientos de segundos); las que desaparecieron"
echo "fueron eliminadas por EVICCION al alcanzar maxmemory. Una sesion evictada se comporta como una"
echo "sesion inexistente: el usuario debe iniciar sesion de nuevo."

echo
echo "=== 3. Politica noeviction: se escribe otro lote de 6000 claves ==="
redis-cli CONFIG SET maxmemory-policy noeviction
evict_ne_antes=$(valor_info evicted_keys)
lote "prueba:presion2" 6000 | redis-cli > "$TMP/r2.txt" 2>&1
ok2=$(contar '^OK' "$TMP/r2.txt"); oom2=$(contar '^OOM' "$TMP/r2.txt")
echo "Escrituras OK: $ok2 | rechazadas por OOM: $oom2"
echo "evicted_keys: $evict_ne_antes -> $(valor_info evicted_keys) (con noeviction no se elimina nada)"
echo "Ejemplo de respuesta de error: $(grep -m1 '^OOM' "$TMP/r2.txt")"
echo "Lectura: la aplicacion debe manejar el error OOM; el dato existente se conserva pero no se aceptan datos nuevos."

echo
echo "=== 4. Restauracion ==="
redis-cli CONFIG SET maxmemory "$limite_original"
redis-cli CONFIG SET maxmemory-policy "$politica_original"
b1=$(borrar_prefijo "prueba:presion")
echo "Claves de prueba borradas: $b1"
sh "$AQUI/ejecutar_bloques.sh" "$AQUI/carga_muestra.redis" carga
echo "maxmemory: $(valor_info maxmemory_human) | politica: $(valor_info maxmemory_policy) | sesiones: $(listar_claves "sesion:*" | sort -u | wc -l | tr -d ' ')"
