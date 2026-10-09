#!/bin/sh
# =============================================================================
# Hito 7 - Cache de usuarios y sesiones del Fixture 2030 (Grupo 8)
# ejecutar_bloques.sh : ejecutor de los scripts .redis. Corre DENTRO del
# contenedor (usa solo sh y redis-cli, que ya trae la imagen oficial).
#
# Por que existe: redis-cli no admite comentarios (#) cuando lee comandos desde
# un archivo ("ERR unknown command '#'"). Este ejecutor lee el .redis, muestra
# los comentarios, envia cada comando a redis-cli y muestra su respuesta, de
# modo que el log sirve directamente como evidencia (RF13, RNF9).
#
# Uso (dentro del contenedor; /scripts es la carpeta scripts/ montada):
#   sh /scripts/ejecutar_bloques.sh /scripts/sesiones.redis            # modo paso
#   sh /scripts/ejecutar_bloques.sh /scripts/carga_muestra.redis carga # modo carga
#
# Modo "paso" (por defecto): para cada linea
#   - "# texto"          se muestra tal cual (comentario).
#   - "#@esperar N"      pausa N segundos (para observar un vencimiento por TTL).
#   - "#@campos a|b|c"   el proximo INFO muestra solo esos campos (evidencia concisa).
#   - "COMANDO ..."      se muestra como "> COMANDO ..." y luego su respuesta.
#   - MULTI ... EXEC     se envia como una unidad por UNA sola conexion, porque
#                        MULTI/EXEC solo funciona dentro de la misma conexion.
# Modo "carga": filtra comentarios y lineas vacias y envia todos los comandos por
#   una sola conexion; informa cuantos se enviaron y si hubo respuestas de error.
# =============================================================================
archivo="$1"
modo="${2:-paso}"

if [ -z "$archivo" ] || [ ! -f "$archivo" ]; then
  echo "Uso: sh ejecutar_bloques.sh <archivo.redis> [paso|carga]" >&2
  exit 1
fi
if [ "$(redis-cli PING 2>/dev/null)" != "PONG" ]; then
  echo "Redis no responde PONG. Revisar: docker compose ps / docker compose logs redis" >&2
  exit 1
fi

limpio=$(mktemp)
buf=$(mktemp)
trap 'rm -f "$limpio" "$buf"' EXIT
tr -d '\r' < "$archivo" > "$limpio"      # tolera archivos con fin de linea de Windows

# ------------------------------------------------------------------ modo carga
if [ "$modo" = "carga" ]; then
  comandos=$(mktemp)
  respuestas=$(mktemp)
  grep -v '^[[:space:]]*#' "$limpio" | grep -v '^[[:space:]]*$' > "$comandos"
  total=$(wc -l < "$comandos" | tr -d ' ')
  redis-cli < "$comandos" > "$respuestas" 2>&1
  errores=$(grep -cE '^(ERR|WRONGTYPE|OOM|EXECABORT|NOAUTH|MISCONF|LOADING) ' "$respuestas")
  echo "Archivo: $archivo"
  echo "Comandos enviados: $total"
  echo "Respuestas con error: $errores"
  echo "Respuestas mas frecuentes (cantidad, respuesta):"
  sort "$respuestas" | uniq -c | sort -rn | head -6 | sed 's/^/  /'
  if [ "$errores" != "0" ]; then
    echo "Primeras respuestas de error:"
    grep -E '^(ERR|WRONGTYPE|OOM|EXECABORT|NOAUTH|MISCONF|LOADING) ' "$respuestas" | head -5 | sed 's/^/  /'
  fi
  rm -f "$comandos" "$respuestas"
  [ "$errores" = "0" ]
  exit $?
fi

# ------------------------------------------------------------------- modo paso
set -f                                   # sin expansion de comodines (MATCH sesion:*)
en_multi=0
campos=""
while IFS= read -r linea || [ -n "$linea" ]; do
  case "$linea" in
    "#@esperar "*)
      seg="${linea#\#@esperar }"
      printf '[pausa de %s s]\n' "$seg"
      sleep "$seg"
      ;;
    "#@campos "*)
      campos="${linea#\#@campos }"
      ;;
    "#"*)
      printf '%s\n' "$linea"
      ;;
    "")
      [ "$en_multi" = "0" ] && printf '\n'
      ;;
    *)
      printf '> %s\n' "$linea"
      set -- $linea
      verbo=$(printf '%s' "$1" | tr 'a-z' 'A-Z')
      if [ "$en_multi" = "1" ]; then
        printf '%s\n' "$linea" >> "$buf"
        if [ "$verbo" = "EXEC" ] || [ "$verbo" = "DISCARD" ]; then
          redis-cli --no-raw < "$buf" 2>&1 | sed 's/^/  /'
          en_multi=0
        fi
      elif [ "$verbo" = "MULTI" ]; then
        en_multi=1
        printf '%s\n' "$linea" > "$buf"
      elif [ "$verbo" = "INFO" ]; then
        # INFO devuelve texto multilinea: se muestra en crudo (opcionalmente filtrado)
        if [ -n "$campos" ]; then
          printf '%s\n' "$linea" | redis-cli 2>&1 | tr -d '\r' | grep -E "^($campos):" | sed 's/^/  /'
        else
          printf '%s\n' "$linea" | redis-cli 2>&1 | tr -d '\r' | sed 's/^/  /'
        fi
        campos=""
      else
        printf '%s\n' "$linea" | redis-cli --no-raw 2>&1 | sed 's/^/  /'
      fi
      ;;
  esac
done < "$limpio"
