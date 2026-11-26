# Hito 13 — Monitoreo con Prometheus y Grafana, y defensa final del Fixture 2030

**Grupo 8** · Repositorio: https://github.com/franreyna6/ing-de-datos-2 · Teoría: Clase 14 (*Observabilidad con Prometheus + Grafana*)

Capa de observabilidad de la plataforma: Prometheus recolecta métricas de la API integrada (Hito 10) y de las seis bases (Hitos 4 a 9), Grafana las muestra en el tablero **"Fixture 2030 - War Room"** y Alertmanager recibe las alertas. Incluye una prueba de falla controlada bajo carga, con su evidencia, y el material de la defensa ante la FIFA.

> **Lo que se defiende son las bases y las decisiones de arquitectura** (Clase 14: *"No defienden el código, DEFIENDEN LAS BASES"*). Grafana, Swagger y Postman son medios para demostrarlo. El argumento completo está en [`docs/decisiones_de_arquitectura.md`](docs/decisiones_de_arquitectura.md) y [`docs/defensa_final.md`](docs/defensa_final.md).

## Contenido

| Ruta | Qué hay |
| :--- | :--- |
| `docker-compose.yml` | Prometheus, Alertmanager, blackbox_exporter, redis_exporter, mongodb_exporter, Grafana y el renderizador de capturas |
| `prometheus.yml` | Intervalo de scrape, targets, etiquetas y relación entre cada job y el componente que observa |
| `prometheus/reglas-o-alertas.yml` | 7 alertas con métrica, condición, duración, severidad, impacto, acción y razón del umbral |
| `alertmanager/`, `blackbox/` | Configuración de Alertmanager y de las sondas externas |
| `grafana/` | Datasource y tablero provisionados ([`grafana/README.md`](grafana/README.md) explica cada panel) |
| `scripts/` | Iniciar, verificar targets, diagnosticar bases, prueba controlada, capturas, limpiar y corrida completa (`.ps1`, `.sh` y `.py`) |
| `docs/` | Inventario, métricas y consultas PromQL, alertas, decisiones de arquitectura, limitaciones y defensa |
| `evidencia/` | Targets verificados, prueba de falla, capturas del tablero y resultados sin secretos |
| `defensa/` | Presentación, guion de 20 minutos y demo paso a paso |
| `../api/app/core/metricas.py` | Instrumentación de la API: endpoint `/metrics` (RF4) |
| `../api/app/core/cortocircuito.py` | Corte rápido por base: la mejora transversal que salió de la evidencia (RF12) |

## Requisitos

- Docker Desktop con `docker compose`.
- Las bases de los Hitos 4 a 9 creadas y con sus datos de laboratorio. Ver "Datos de laboratorio" más abajo.
- El entorno de la API del Hito 10 (`api/.venv`). Si falta, crearlo con el README de `api/`. `prometheus_client` se instala solo.
- Puertos libres en `127.0.0.1`: 3000 (Grafana), 9090 (Prometheus), 9093 (Alertmanager), 9115 (blackbox) y 8000 (API).

## Opción 1: todo en un comando

Desde la raíz del repositorio, con Docker Desktop abierto:

```powershell
.\monitoreo\scripts\ejecutar_todo_h13.ps1          # Windows (PowerShell)
./monitoreo/scripts/ejecutar_todo_h13.sh           # Linux / macOS
```

Tarda unos 20 minutos y hace lo siguiente:

1. Inicia las seis bases. Si un contenedor ya existe, solo hace `docker start`: no lo recrea ni toca sus datos.
2. Levanta el monitoreo.
3. Levanta la API con la caché del Hito 12 encendida y espera a que `/salud` vea las seis bases.
4. Verifica los targets.
5. Corre la prueba de falla controlada bajo carga: caída de Redis y, después, de Cassandra.
6. Guarda informe, series y capturas.
7. Verifica los targets otra vez y detiene la API.

Las bases y el monitoreo quedan corriendo para la demo. Toda la salida queda en `evidencia/resultados_sin_secretos/ejecucion_<etiqueta>.log`.

Con `--sin-cortocircuito` la API se levanta sin el corte rápido (`CORTOCIRCUITO_S=0`, comportamiento del Hito 12), para comparar con la mejora.

## Opción 2: paso a paso

```powershell
# 1. Bases y monitoreo (crea monitoreo/.env y monitoreo/secretos/, fuera de Git)
.\monitoreo\scripts\iniciar_monitoreo.ps1 --con-bases

# 2. API del Hito 10 con métricas (terminal aparte; la caché del Hito 12 es opcional)
cd api; .\.venv\Scripts\Activate.ps1
$env:CACHE_COMENTARIOS_TTL_S = "2"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd ..

# 3. Verificar que Prometheus lee cada target (guarda evidencia/prometheus_targets.*)
.\monitoreo\scripts\verificar_targets.ps1 --esperar 60

# 4. Prueba de falla controlada bajo carga (unos 12 minutos)
.\monitoreo\scripts\ejecutar_prueba_controlada.ps1

# 5. Capturas del tablero de los últimos 15 minutos (opcional)
api\.venv\Scripts\python.exe monitoreo\scripts\capturar_dashboard.py --ultimos-minutos 15
```

En Linux o macOS se usan los mismos scripts con extensión `.sh`.

## Acceso

| Servicio | URL | Para qué |
| :--- | :--- | :--- |
| Grafana | http://localhost:3000 | Tablero *Fixture 2030 - War Room* (página de inicio). Sin login: solo lectura. El administrador está en `monitoreo/.env`. |
| Prometheus | http://localhost:9090 | `Status → Targets` (estado de cada target), `Alerts` (reglas) y `Graph` (PromQL) |
| Alertmanager | http://localhost:9093 | Alertas recibidas y su agrupación por severidad |
| API | http://localhost:8000/docs y `/metrics` | Swagger y métricas en formato Prometheus |

## Validar que un target está UP

1. En http://localhost:9090/targets cada target tiene que estar en **UP**. En los jobs `sonda-*`, además, `probe_success` tiene que valer 1: la sonda llegó a la base.
2. O bien con `.\monitoreo\scripts\verificar_targets.ps1`, que imprime una tabla, termina con código distinto de 0 si algo falla y deja la evidencia en `evidencia/prometheus_targets.md`.
3. En PromQL: `up` (1 = UP) y `probe_success` (1 = la base aceptó la conexión).

## Investigar un target DOWN

1. Leer el error del target en `Status → Targets`, o en la columna *Último error* de `evidencia/prometheus_targets.md`:
   - `connection refused`: no hay nada escuchando.
   - `context deadline exceeded`: tardó más que el timeout de 10 s.
   - `401`: falta un token.
   - `server returned HTTP status 404`: la ruta está mal.
2. Correr `.\monitoreo\scripts\diagnosticar_bases.ps1`. Guarda en `evidencia/resultados_sin_secretos/diagnostico_<fecha>.txt` el estado, la salud, los puertos, los montajes y el log de cada contenedor de las bases.
3. Si un contenedor está detenido: `docker start <contenedor>` (nunca `down -v`).
4. Probar el endpoint desde la máquina: `curl http://localhost:<puerto>/metrics`. Si responde desde la máquina pero no desde Prometheus, el problema es el camino `host.docker.internal`, no la base.
5. Casos conocidos:

| Target | Causa típica | Qué hacer |
| :--- | :--- | :--- |
| `api-fixture` | La API no está corriendo o corre código sin `/metrics` | Levantarla (paso 2) y abrir http://localhost:8000/metrics |
| `influxdb` | `401`: falta el token o `monitoreo/secretos/influxdb3-token` está vacío | Verificar que exista `influxdb/.influxdb3-token` (Hito 8) y volver a correr `iniciar_monitoreo` |
| `iris` | IRIS todavía arrancando (tarda 1 a 2 minutos). En Windows, contenedor creado sin el volumen de Docker: IRIS no puede hacer `chown` de `/durable` y no abre sus puertos (README del Hito 9). | Esperar. Si no levanta: `cd iris; .\scripts\ejecutar_todo.ps1 -VolumenDocker` |
| `mongodb` | El exporter no puede autenticarse | Revisar `MONGODB_EXPORTER_URI` en `monitoreo/.env` |
| `sonda-tcp` de Cassandra | El nodo está arrancando (1 a 2 minutos) | Esperar a que `/salud` de la API la vea disponible |

Si se cambia la configuración, Prometheus se recarga sin reiniciar: `curl -X POST http://localhost:9090/-/reload`.

## Datos de laboratorio

El monitoreo no carga datos propios: observa los que cada hito ya cargó en su base. Si alguna base se reconstruye desde cero, se carga con el script de su carpeta.

| Base | Carga |
| :--- | :--- |
| MongoDB (Hito 4) | `mongodb/run-all.sh` |
| Neo4j (Hito 5) | `neo4j/queries/carga.cypher` |
| Cassandra (Hito 6) | `cassandra/scripts/ejecutar_todo.ps1` |
| Redis (Hito 7) | `redis/scripts/ejecutar_todo.ps1` |
| InfluxDB (Hito 8) | `influxdb/scripts/ejecutar_todo.ps1` |
| IRIS (Hito 9) | `iris/scripts/ejecutar_todo.ps1 -VolumenDocker` |

La prueba de carga del Hito 13 escribe comentarios **solo** en partidos de laboratorio propios de cada corrida (`H13-<etiqueta>-P1/P2`), nunca en partidos reales del fixture (RNF5).

## Repetir la demostración

El paso a paso de la demo, con lo que se muestra y el plan B si algo falla, está en [`defensa/demo.md`](defensa/demo.md).

## Seguridad (RNF6)

- `monitoreo/.env` (contraseña de Grafana generada al azar y URI del exporter de Mongo) y `monitoreo/secretos/` (token de InfluxDB) están en `.gitignore`.
- Prometheus lee el token de InfluxDB desde un archivo (`credentials_file`); el token no aparece en ningún `.yml`.
- Todos los puertos se publican solo en `127.0.0.1`.
- Los scripts pasan toda la evidencia por `enmascarar()` (`scripts/lib_monitoreo.py`) antes de escribirla.
- El tablero y las capturas muestran métricas, nunca credenciales.

## Trazabilidad (RNF2)

Cada archivo de evidencia lleva la fecha UTC y el commit del repositorio. Cada prueba tiene una **etiqueta** (`AAAAMMDD-HHMMSS`) que aparece en el nombre de su carpeta, en sus capturas, en las anotaciones del tablero y en los partidos de laboratorio que escribió.

## Detener y limpiar (RNF11)

```powershell
.\monitoreo\scripts\limpiar_entorno.ps1                              # docker compose down del monitoreo (conserva datos)
.\monitoreo\scripts\limpiar_entorno.ps1 --detener-bases              # además docker stop de las 6 bases (no las borra)
.\monitoreo\scripts\limpiar_entorno.ps1 --datos-de-prueba <etiqueta>              # muestra qué borraría de esa corrida
.\monitoreo\scripts\limpiar_entorno.ps1 --datos-de-prueba <etiqueta> --confirmar  # borra solo esos datos de laboratorio
.\monitoreo\scripts\limpiar_entorno.ps1 --borrar-datos-monitoreo     # además borra el historial de Prometheus y Grafana
```

Ningún script borra volúmenes de las bases.
