#!/usr/bin/env bash
# Hito 9 - Flujo completo en Linux/macOS: levanta IRIS, compila las clases,
# carga los datos y ejecuta los bloques de demostracion. Deja el log como
# evidencia en docs/evidencia/logs/. Requiere Docker con docker compose.
#
# Uso (desde la carpeta iris/):
#   ./scripts/ejecutar_todo.sh                         # flujo normal
#   ./scripts/ejecutar_todo.sh --reiniciar             # borra el dominio y recarga desde cero
#   ./scripts/ejecutar_todo.sh --probar-persistencia   # ademas reinicia el contenedor y recuenta
#
# Cada bloque corre en una sesion nueva del Terminal de IRIS (proceso limpio).
set -u
cd "$(dirname "$0")/.."
REINICIAR=0; PERSIST=0
for arg in "$@"; do
  case "$arg" in
    --reiniciar) REINICIAR=1 ;;
    --probar-persistencia) PERSIST=1 ;;
    *) echo "Argumento desconocido: $arg"; exit 2 ;;
  esac
done
export HOME="${HOME:-$(cd ~ && pwd)}"
MARCA="$(date +%Y%m%d_%H%M%S)"
mkdir -p docs/evidencia/logs
LOG="docs/evidencia/logs/ejecucion_${MARCA}.log"
CONTENEDOR="fixture2030-iris"

# Ejecuta comandos ObjectScript en una sesion nueva del Terminal (namespace USER).
iris_cmd() {
  printf '%s\nHalt\n' "$1" | docker exec -i "$CONTENEDOR" iris session IRIS -U USER
}

paso() {            # paso "titulo" comando...
  local titulo="$1"; shift
  { echo; echo "######## $titulo ########"; } | tee -a "$LOG"
  "$@" 2>&1 | tee -a "$LOG"
}

esperar_iris() {
  echo "Esperando a que IRIS acepte sesiones (el primer inicio copia Durable %SYS y tarda)..."
  for _ in $(seq 1 60); do
    if iris_cmd 'Write "IRIS-LISTO",!' 2>/dev/null | grep -q "IRIS-LISTO"; then echo "IRIS listo."; return 0; fi
    sleep 5
  done
  echo "IRIS no respondio en 5 minutos. Revisar: docker compose logs iris"; return 1
}

{
  echo "Hito 9 - ejecucion $MARCA"
  echo "Fecha local: $(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "Equipo: $(uname -srm) | nucleos: $(nproc 2>/dev/null || sysctl -n hw.ncpu) | Docker: $(docker --version)"
} | tee "$LOG"

# Permisos segun el instructivo de la Clase 10: solo al crear la carpeta (despues
# los archivos pertenecen al usuario de IRIS dentro del contenedor).
paso "0. Directorio durable ~/docker/data/iris" bash -c '
  if [ ! -d "$HOME/docker/data/iris" ]; then
    mkdir -p "$HOME/docker/data/iris" && chmod 777 "$HOME/docker/data/iris"
  fi
  ls -ld "$HOME/docker/data/iris"'
paso "1. docker compose up -d" docker compose up -d
paso "1b. Espera del servicio" esperar_iris
if ! grep -q "IRIS listo." "$LOG"; then echo "SE DETIENE: IRIS no esta disponible." | tee -a "$LOG"; exit 1; fi
paso "1c. Version de IRIS y contenedor" bash -c "docker compose ps; printf 'Write \$ZVersion,!\nHalt\n' | docker exec -i $CONTENEDOR iris session IRIS -U USER"

paso "2. Carga y compilacion de las clases .cls" iris_cmd 'Set sc=$system.OBJ.LoadDir("/iris/src","ck",.err,1) Write !,"COMPILACION: ",$Select($System.Status.IsOK(sc):"OK",1:$System.Status.GetErrorText(sc)),!'
if ! grep -q "COMPILACION: OK" "$LOG"; then echo "SE DETIENE: las clases no compilaron (ver el detalle arriba)." | tee -a "$LOG"; exit 1; fi

[ "$REINICIAR" -eq 1 ] && paso "2b. Reinicio del dominio" iris_cmd 'Do ##class(Fixture.Carga).Reiniciar()'
paso "3. Bloque 1 - Carga inicial (RF6)"             iris_cmd 'Do ##class(Fixture.Demo).Bloque1Carga()'
paso "4. Bloque 2 - Arbol con un solo %Save (RF6)"   iris_cmd 'Do ##class(Fixture.Demo).Bloque2ArbolAtomico()'
paso "5. Bloque 3 - Fallo controlado (RF5)"          iris_cmd 'Do ##class(Fixture.Demo).Bloque3FalloControlado()'
paso "6. Bloque 4 - Navegacion por objetos (RF7)"    iris_cmd 'Do ##class(Fixture.Demo).Bloque4Navegacion()'
paso "7. Bloque 5 - Proyeccion SQL (RF8)"            iris_cmd 'Do ##class(Fixture.Demo).Bloque5ProyeccionSQL()'
paso "8. Bloque 6 - Validaciones (RF9)"              iris_cmd 'Do ##class(Fixture.Demo).Bloque6Validaciones()'
paso "9. Bloque 7 - Integridad ante borrados (RF3)"  iris_cmd 'Do ##class(Fixture.Demo).Bloque7Integridad()'

if [ "$PERSIST" -eq 1 ]; then
  paso "10. Persistencia: conteo antes de reiniciar" iris_cmd 'Do ##class(Fixture.Demo).Conteo()'
  paso "10b. docker compose down + up -d (se recrea el contenedor)" bash -c "docker compose down && docker compose up -d"
  paso "10c. Espera del servicio" esperar_iris
  paso "10d. Persistencia: conteo despues de recrear el contenedor" iris_cmd 'Do ##class(Fixture.Demo).Conteo()'
fi
echo; echo "Fin. Log: $LOG" | tee -a "$LOG"
