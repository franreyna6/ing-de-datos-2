# Entorno de ejecución

## Servicios que intervienen

| Servicio | Dónde se define | Rol en la prueba |
| :--- | :--- | :--- |
| Cassandra (`fixture2030-cassandra`) | `cassandra/docker-compose.yml` (Hito 6) | Fuente operacional de los comentarios: recibe las escrituras y, sin caché, todas las lecturas. |
| Redis (`fixture2030-redis`) | `redis/docker-compose.yml` (Hito 7) | Caché de lectura en la versión optimizada. Configuración del Hito 7: `maxmemory 100mb`, `volatile-lru`. |
| API FastAPI | `api/` (Hito 10) | Único punto de entrada de la carga. Corre fuera de Docker, en el `.venv` de la API. |
| Generador de carga | `carga-optimizacion/scripts/` | Proceso de Python en la misma notebook. |

No hace falta levantar MongoDB, Neo4j, InfluxDB ni IRIS: el flujo elegido no los usa. `/salud` los va a informar como no disponibles, y eso no afecta la prueba. Que no estén levantados también libera recursos de la notebook (RNF9).

## Qué se registra automáticamente en cada corrida

Todo esto queda en `metadata.json`, dentro de la carpeta de la corrida:

- **Fecha y hora** UTC de inicio y fin, y **duración real**.
- **Commit** de git, y si había cambios sin commitear en `api/` o en los scripts. Si los hay, `comparar_resultados.py` lo marca.
- **Versión observada** de Cassandra (`release_version`), de Redis (`redis_version`) y de Docker. Las imágenes usan la etiqueta `latest`, así que se registra la versión que efectivamente corrió.
- **Sistema operativo**, procesador, núcleos, memoria total y versión de Python del generador.
- **Escenario completo**, con el hash de `escenario.json` y el hash del plan de datos.
- **Indicio del cliente de Cassandra** que usa la API: el driver nativo o el modo de respaldo con `cqlsh`. La confirmación está en el log de la API (`modo=driver` o `modo=cqlsh`). Las dos corridas tienen que usar el mismo cliente para que la comparación sea válida.

## Comandos equivalentes en bash (Linux, macOS o Git Bash)

En la terminal A (API):

```bash
cd api && . .venv/bin/activate
CACHE_COMENTARIOS_TTL_S=0 python -m uvicorn app.main:app --port 8000 \
  > ../carga-optimizacion/docs/evidencia/logs_api/api_linea_base.log 2>&1
```

En la terminal B (generador):

```bash
. api/.venv/bin/activate
python carga-optimizacion/scripts/ejecutar_linea_base.py
```

## Límites de la notebook y controles (RNF9)

- La carga máxima es de **60 usuarios virtuales** durante 20 s, en la fase de pico. Cada usuario espera entre 0,1 y 0,3 s entre operaciones, así que no hay ráfagas sin control.
- El **corte seguro** (`corte_seguro` en `escenario.json`) detiene la prueba si en los últimos 10 s la tasa de error supera el 30 % o el p95 supera los 5 s. Lo medido hasta ese momento se guarda y la corrida queda marcada como interrumpida.
- Con `Ctrl+C` la prueba también se detiene de forma ordenada: se esperan las requests en vuelo y se guardan los resultados.
- `docker stats` se consulta cada 3 s, que es un costo bajo. El muestreo se hace en el mismo proceso que el generador, así que su costo aparece dentro de `generador_cpu_pct`.
- Si la notebook no alcanza, se puede usar `--escala 0.5` (mitad de usuarios). Hay que usar el **mismo** valor en las dos corridas.
- Conviene correr con la notebook enchufada, con otras aplicaciones pesadas cerradas, y con las mismas condiciones en las dos corridas. Las diferencias que no se puedan controlar se anotan en `docs/linea_base.md`.

## Uvicorn sin `--reload` y con el log a un archivo

`api/scripts/iniciar_api.ps1` usa `--reload`, que agrega un proceso que vigila los archivos. Para medir se arranca uvicorn directamente y sin esa opción.

La API escribe una línea de log por request y otra por cada acceso a la base. Imprimirlas en la consola durante la carga puede frenar la propia API (la Clase 13 menciona los logs excesivos como un posible cuello de botella). Por eso el log va a un archivo, y en las dos corridas se hace de la misma forma.
