#!/bin/sh
# =============================================================================
# concurrencia_paralela.sh - Hito 7 (Grupo 8)
# Prueba de operaciones concurrentes con VARIOS clientes redis-cli en paralelo
# sobre la MISMA clave (RF8, RF13). Corre dentro del contenedor.
#
# Compara, con la misma cantidad de clientes y de operaciones:
#   1. INCR                      (comando nativo atomico)
#   2. ZINCRBY                   (voto en Sorted Set, atomico)
#   3. MULTI/EXEC                (actividad de sesion como unidad)
#   4. GET + suma + SET          (ANTIPATRON leer-modificar-escribir)
# Los tres primeros deben dar exactamente el total esperado. El cuarto pierde
# actualizaciones porque otro cliente se intercala entre el GET y el SET.
#
# Uso: sh /scripts/concurrencia_paralela.sh
#      CLIENTES=8 N=1000 M=200 sh /scripts/concurrencia_paralela.sh   (otros tamanos)
# Las claves usan el prefijo prueba:par: y TTL de 600 s (RNF6).
# =============================================================================
. "$(dirname "$0")/lib_redis.sh"

CLIENTES="${CLIENTES:-4}"     # clientes simultaneos
N="${N:-500}"                 # operaciones por cliente en las pruebas atomicas
M="${M:-100}"                 # iteraciones por cliente en el antipatron (2 procesos por iteracion)

echo "Fecha de ejecucion (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Clientes simultaneos: $CLIENTES | operaciones por cliente: $N (atomicas) y $M (antipatron)"
echo

# ---- preparacion: claves de prueba con TTL, creadas de forma repetible ----
redis-cli SET prueba:par:atomico 0 EX 600 > /dev/null
redis-cli SET prueba:par:antipatron 0 EX 600 > /dev/null
redis-cli DEL prueba:par:votos > /dev/null
redis-cli DEL prueba:par:sesion > /dev/null
printf 'MULTI\nZADD prueba:par:votos 0 jugador-A\nEXPIRE prueba:par:votos 600\nEXEC\n' | redis-cli > /dev/null
printf 'MULTI\nHSET prueba:par:sesion usuario_id U9200 acciones 0\nEXPIRE prueba:par:sesion 600\nEXEC\n' | redis-cli > /dev/null

# ---- 1. INCR paralelo ----
c=1
while [ "$c" -le "$CLIENTES" ]; do
  ( seq 1 "$N" | awk '{print "INCR prueba:par:atomico"}' | redis-cli > /dev/null ) &
  c=$((c + 1))
done
wait
incr=$(redis-cli GET prueba:par:atomico)

# ---- 2. ZINCRBY paralelo (votos) ----
c=1
while [ "$c" -le "$CLIENTES" ]; do
  ( seq 1 "$N" | awk '{print "ZINCRBY prueba:par:votos 1 jugador-A"}' | redis-cli > /dev/null ) &
  c=$((c + 1))
done
wait
votos=$(redis-cli ZREVRANGE prueba:par:votos 0 0 WITHSCORES | tail -n 1)

# ---- 3. MULTI/EXEC paralelo (actividad de sesion) ----
c=1
while [ "$c" -le "$CLIENTES" ]; do
  ( seq 1 "$N" | awk '{print "MULTI"; print "HSET prueba:par:sesion ultimo_acceso 2030-06-14T21:00:00Z"; print "HINCRBY prueba:par:sesion acciones 1"; print "EXPIRE prueba:par:sesion 1800"; print "EXEC"}' | redis-cli > /dev/null ) &
  c=$((c + 1))
done
wait
acciones=$(redis-cli HGET prueba:par:sesion acciones)
ttl_sesion=$(redis-cli TTL prueba:par:sesion)

# ---- 4. ANTIPATRON: GET, sumar en la shell, SET (KEEPTTL conserva el vencimiento) ----
c=1
while [ "$c" -le "$CLIENTES" ]; do
  (
    i=0
    while [ "$i" -lt "$M" ]; do
      v=$(redis-cli GET prueba:par:antipatron)
      redis-cli SET prueba:par:antipatron $((v + 1)) KEEPTTL > /dev/null
      i=$((i + 1))
    done
  ) &
  c=$((c + 1))
done
wait
anti=$(redis-cli GET prueba:par:antipatron)

# ---- resultados ----
esp_atom=$((CLIENTES * N))
esp_anti=$((CLIENTES * M))
veredicto() {  # veredicto <esperado> <obtenido>
  if [ "$1" = "$2" ]; then echo "correcto"; else echo "PERDIO $(($1 - $2)) actualizaciones"; fi
}
printf '%-34s %10s %10s   %s\n' "Prueba" "Esperado" "Obtenido" "Resultado"
printf '%-34s %10s %10s   %s\n' "INCR (atomico)" "$esp_atom" "$incr" "$(veredicto "$esp_atom" "$incr")"
printf '%-34s %10s %10s   %s\n' "ZINCRBY (atomico)" "$esp_atom" "${votos%.*}" "$(veredicto "$esp_atom" "${votos%.*}")"
printf '%-34s %10s %10s   %s\n' "MULTI/EXEC (acciones de sesion)" "$esp_atom" "$acciones" "$(veredicto "$esp_atom" "$acciones")"
printf '%-34s %10s %10s   %s\n' "GET+SET (antipatron)" "$esp_anti" "$anti" "$(veredicto "$esp_anti" "$anti")"
echo
echo "TTL de la sesion tras las renovaciones concurrentes: $ttl_sesion s (esperado: cerca de 1800, nunca -1 ni -2)"
echo "Nota: el antipatron pierde actualizaciones por intercalado; la cantidad varia en cada corrida."
