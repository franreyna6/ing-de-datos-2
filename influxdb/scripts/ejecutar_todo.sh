#!/usr/bin/env bash
# Hito 8 - Ejecuta el flujo completo en Linux/macOS y deja el log como evidencia
# en docs/evidencia/logs/. Requiere Docker y Python 3.8+.
#
# Uso (desde la carpeta influxdb/):
#   ./scripts/ejecutar_todo.sh [muestra|local|completo] [--medir-lotes] [--probar-persistencia]
set -u
cd "$(dirname "$0")/.."
PERFIL="local"; MEDIR=0; PERSIST=0
for arg in "$@"; do
  case "$arg" in
    muestra|local|completo) PERFIL="$arg" ;;
    --medir-lotes) MEDIR=1 ;;
    --probar-persistencia) PERSIST=1 ;;
    *) echo "Argumento desconocido: $arg"; exit 2 ;;
  esac
done
export HOME="${HOME:-$(cd ~ && pwd)}"
export PYTHONUNBUFFERED=1   # que la salida de Python se vea en vivo
PY="$(command -v python3 || command -v python)"
MARCA="$(date +%Y%m%d_%H%M%S)"
mkdir -p docs/evidencia/logs
LOG="docs/evidencia/logs/ejecucion_${PERFIL}_${MARCA}.log"
FALLOS=0

paso() {            # paso "titulo" comando...
  local titulo="$1"; shift
  { echo; echo "######## $titulo ########"; } | tee -a "$LOG"
  "$@" 2>&1 | tee -a "$LOG"
  local rc="${PIPESTATUS[0]}"
  if [ "$rc" -ne 0 ]; then echo "!! el paso termino con codigo $rc" | tee -a "$LOG"; FALLOS=$((FALLOS+1)); fi
}

{
  echo "Hito 8 - ejecucion $MARCA | perfil: $PERFIL"
  echo "Fecha local: $(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "Equipo: $(uname -srm) | nucleos: $(nproc 2>/dev/null || sysctl -n hw.ncpu) | RAM: $(free -h 2>/dev/null | awk '/Mem:/{print $2}')"
  echo "Python: $($PY --version 2>&1) | Docker: $(docker --version)"
} | tee "$LOG"

paso "1. Inicializacion (compose, token local, bases)" "$PY" scripts/inicializacion.py
if [ "$FALLOS" -gt 0 ]; then echo "SE DETIENE: fallo la inicializacion. Verificar que Docker este activo (docker version)." | tee -a "$LOG"; exit "$FALLOS"; fi
paso "2. Generacion de puntos ($PERFIL)" "$PY" scripts/generacion_puntos.py --perfil "$PERFIL"
paso "3. Carga por lotes" "$PY" scripts/carga_lotes.py --perfil "$PERFIL"
if [ "$FALLOS" -gt 0 ]; then echo "SE DETIENE: la carga tuvo lotes rechazados o se aborto." | tee -a "$LOG"; exit "$FALLOS"; fi
[ "$MEDIR" -eq 1 ] && paso "3b. Medicion de tamano de lote y concurrencia" "$PY" scripts/carga_lotes.py --perfil "$PERFIL" --medir-lotes
paso "4. Consultas temporales" "$PY" scripts/consultas_temporales.py
paso "5. Agregaciones y resumen de 1 minuto" "$PY" scripts/agregaciones.py
paso "6. Validacion" "$PY" scripts/validacion.py --perfil "$PERFIL"
if [ "$PERSIST" -eq 1 ]; then
  paso "7. Persistencia: conteo, reinicio del contenedor y nuevo conteo" "$PY" scripts/persistencia.py
fi
echo; echo "Resumen: $FALLOS paso(s) con error. Log: $LOG" | tee -a "$LOG"
exit "$FALLOS"
