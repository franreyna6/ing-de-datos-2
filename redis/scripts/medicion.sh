#!/bin/sh
# =============================================================================
# medicion.sh - Hito 7 (Grupo 8)
# Prueba de las operaciones principales (RF12, RNF10). Corre dentro del contenedor.
#
# METODO
#   A. Tiempo de comandos: se arma un archivo con N comandos iguales y se envia por
#      UNA conexion de redis-cli (un comando a la vez, esperando su respuesta, sin
#      pipelining). Se mide el tiempo total con date. El resultado incluye la
#      lectura del archivo y el procesamiento de redis-cli: es una cota del tiempo
#      por comando visto desde un cliente simple, NO la capacidad maxima de Redis.
#   B. Tasa de hit del patron Cache-Aside: se parte de la cache de partidos VACIA y se
#      ejecuta un bucle Cache-Aside real (GET; si falta, leer la "fuente" y SET con
#      EX 300) sobre una secuencia reproducible de solicitudes: 80% a los 20 partidos
#      mas consultados (F2030-001 a F2030-020) y 20% uniforme sobre los 96. La tasa
#      se calcula a partir de los contadores del servidor (INFO stats) y se verifica
#      contra los contadores del propio bucle.
#
# LIMITACIONES: ambiente de laboratorio de un solo nodo, cliente en el mismo equipo
#   (sin red), sin carga competidora, secuencia sintetica. Los numeros no son
#   extrapolables a produccion; sirven para comparar operaciones entre si y para
#   verificar el comportamiento. Ver docs/rendimiento.md.
#
# Uso: sh /scripts/medicion.sh
#      N=20000 SOLICITUDES=5000 sh /scripts/medicion.sh   (otros tamanos)
# Requiere /datos/origen/partidos.csv (el Compose monta ./data en /datos).
# =============================================================================
. "$(dirname "$0")/lib_redis.sh"

N="${N:-5000}"                          # comandos por operacion en la parte A
SOLICITUDES="${SOLICITUDES:-1000}"      # solicitudes de la parte B
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "=== Ambiente de la medicion ==="
echo "Fecha de ejecucion (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Redis (version observada): $(valor_info redis_version)"
echo "Nucleos visibles en el contenedor: $(nproc)"
echo "Memoria total visible en el contenedor: $(awk '/MemTotal/ {print $2 " kB"}' /proc/meminfo)"
echo "Kernel: $(uname -sr)"
echo "Parametros: N=$N comandos por operacion, SOLICITUDES=$SOLICITUDES"
echo

# --------------------------------------------------------------------------- A
echo "=== A. Tiempo de comandos por una conexion (secuencial, sin pipelining) ==="
redis-cli SET prueba:med:contador 0 EX 600 > /dev/null
redis-cli SET prueba:med:valor '{"codigo":"F2030-001","golesLocal":1,"golesVisitante":1}' EX 600 > /dev/null
printf 'MULTI\nHSET prueba:med:sesion usuario_id U9300 acciones 0\nEXPIRE prueba:med:sesion 600\nEXEC\n' | redis-cli > /dev/null
redis-cli DEL prueba:med:votos > /dev/null
printf 'MULTI\nZADD prueba:med:votos 0 jugador-A\nEXPIRE prueba:med:votos 600\nEXEC\n' | redis-cli > /dev/null

medir() {  # medir <etiqueta> <archivo_de_comandos> <cantidad_de_comandos>
  ini=$(ahora_ms)
  redis-cli < "$2" > /dev/null
  fin=$(ahora_ms)
  ms=$((fin - ini)); [ "$ms" -lt 1 ] && ms=1
  printf '%-34s %8d cmd %8d ms %10d cmd/s %7d us/cmd\n' "$1" "$3" "$ms" $(($3 * 1000 / ms)) $((ms * 1000 / $3))
}

awk -v n="$N" 'BEGIN{for(i=0;i<n;i++) print "INCR prueba:med:contador"}'  > "$TMP/incr.txt"
awk -v n="$N" 'BEGIN{for(i=0;i<n;i++) print "GET prueba:med:valor"}'      > "$TMP/get.txt"
awk -v n="$N" 'BEGIN{for(i=0;i<n;i++) print "HGETALL prueba:med:sesion"}' > "$TMP/hgetall.txt"
awk -v n="$N" 'BEGIN{for(i=0;i<n;i++) print "ZINCRBY prueba:med:votos 1 jugador-A"}' > "$TMP/zincrby.txt"
awk -v n="$N" 'BEGIN{for(i=0;i<n/4;i++){print "MULTI"; print "HINCRBY prueba:med:sesion acciones 1"; print "EXPIRE prueba:med:sesion 1800"; print "EXEC"}}' > "$TMP/multi.txt"

medir "INCR (contador de visitas)"        "$TMP/incr.txt"    "$N"
medir "GET (cache hit, String JSON)"      "$TMP/get.txt"     "$N"
medir "HGETALL (leer sesion completa)"    "$TMP/hgetall.txt" "$N"
medir "ZINCRBY (voto en ranking)"         "$TMP/zincrby.txt" "$N"
medir "MULTI/EXEC (renovar sesion, 4 cmd)" "$TMP/multi.txt"   "$N"
echo

# --------------------------------------------------------------------------- B
echo "=== B. Tasa de hit del patron Cache-Aside (cache de partidos en frio) ==="
if [ ! -f /datos/origen/partidos.csv ]; then
  echo "No se encuentra /datos/origen/partidos.csv (fuente simulada). Revisar el volumen ./data en el Compose." >&2
  exit 1
fi

borrados=$(borrar_prefijo "cache:partido:")
echo "Copias de cache de partidos borradas antes de empezar: $borrados"

# Secuencia reproducible: generador congruencial de Park-Miller con semilla 2030.
# No se usa srand()/rand() de awk porque mawk (Debian) no garantiza la misma secuencia entre corridas.
awk -v n="$SOLICITUDES" '
  function azar() { x = (x * 16807) % 2147483647; return x / 2147483647 }
  BEGIN {
    x = 2030
    for (j = 0; j < 20; j++) azar()                 # descarta los primeros valores (semilla chica)
    for (i = 0; i < n; i++) {
      if (azar() < 0.8) k = int(azar() * 20) + 1; else k = int(azar() * 96) + 1
      printf "F2030-%03d\n", k
    }
  }' > "$TMP/secuencia.txt"
distintos=$(sort -u "$TMP/secuencia.txt" | wc -l | tr -d ' ')

# "Fuente de verdad" simulada: arma la ficha JSON desde partidos.csv (origen del Hito 5)
fuente_partido() {
  grep "^$1," /datos/origen/partidos.csv | tr -d '\r' | awk -F, '{printf "{\"codigo\":\"%s\",\"fecha\":\"%s\",\"fase\":\"%s\",\"grupo\":\"%s\",\"golesLocal\":%d,\"golesVisitante\":%d,\"sedeCodigo\":\"%s\"}", $1,$2,$3,$4,$5,$6,$7}'
}

h0=$(valor_info keyspace_hits)
m0=$(valor_info keyspace_misses)
app_hit=0
app_miss=0
ini=$(ahora_ms)
while read -r cod; do
  v=$(redis-cli GET "cache:partido:$cod")
  if [ -n "$v" ]; then
    app_hit=$((app_hit + 1))                                  # cache hit: se responde desde Redis
  else
    app_miss=$((app_miss + 1))                                # cache miss: leer la fuente y recargar con TTL
    redis-cli SET "cache:partido:$cod" "$(fuente_partido "$cod")" EX 300 > /dev/null
  fi
done < "$TMP/secuencia.txt"
fin=$(ahora_ms)
h1=$(valor_info keyspace_hits)
m1=$(valor_info keyspace_misses)

srv_hit=$((h1 - h0))
srv_miss=$((m1 - m0))
echo "Solicitudes: $SOLICITUDES | partidos distintos pedidos: $distintos | duracion del bucle: $((fin - ini)) ms"
printf '%-30s %10s %10s\n' "" "Aciertos" "Fallos"
printf '%-30s %10d %10d\n' "Contadores del bucle (app)" "$app_hit" "$app_miss"
printf '%-30s %10d %10d\n' "Delta de INFO stats (servidor)" "$srv_hit" "$srv_miss"
awk -v h="$srv_hit" -v m="$srv_miss" 'BEGIN{printf "tasa_de_hit = keyspace_hits / (keyspace_hits + keyspace_misses) x 100 = %.1f %%\n", h*100/(h+m)}'
if [ "$srv_hit" = "$app_hit" ] && [ "$srv_miss" = "$app_miss" ]; then
  echo "Verificacion: los contadores del servidor coinciden con los del bucle."
else
  echo "Verificacion: los contadores NO coinciden (hay otro cliente usando el servidor?)."
fi
echo "Lectura: partir en frio produce un fallo por cada partido distinto (${distintos}); el resto son aciertos."
echo "La tasa depende de la secuencia sintetica y del TTL de 300 s (mayor que la duracion de la prueba)."
