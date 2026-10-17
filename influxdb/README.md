# Hito 8 — Series temporales de estadísticas en vivo (InfluxDB)

**Repositorio del grupo:** https://github.com/franreyna6/ing-de-datos-2 (carpeta `influxdb/`)

Ingeniería de Datos II · Grupo 8 · Fixture Mundial 2030 · Clase 9 (series temporales)

Módulo que registra y recupera las estadísticas que cambian durante cada partido (posesión, pases, tiros, actividad de usuarios, métricas operativas y rendimiento de jugadores) con **InfluxDB 3 Core** en Docker. El volumen objetivo es de **10M+ puntos**: el generador reproduce 10.598.400 puntos con los 96 partidos del Hito 5, y el laboratorio local carga por defecto 1.324.800.

> **Alcance honesto.** Los datos son **simulados**, anclados a los CSV del Hito 5. El laboratorio es un nodo en una máquina: se demuestra la **corrección** del modelo, la carga y las consultas, no el rendimiento de producción. Qué se demuestra y qué no: [`docs/pruebas_y_evidencia.md`](docs/pruebas_y_evidencia.md).

## Requisitos previos

- Docker (Docker Desktop en Windows o macOS) con `docker compose`.
- Python 3.8 o superior. Los scripts usan solo la biblioteca estándar: **no hay que instalar paquetes**.
- Espacio libre: unos 160 MB para el perfil `local` y unos 1,3 GB para `completo`.

## Inicio rápido

Desde la carpeta `influxdb/`.

**Windows (PowerShell):**

```powershell
.\scripts\ejecutar_todo.ps1                  # perfil local: ~1,3 M puntos
.\scripts\ejecutar_todo.ps1 -Perfil muestra  # prueba rápida: 22 mil puntos
.\scripts\ejecutar_todo.ps1 -Perfil completo # objetivo 10M+: 10,6 M puntos
.\scripts\ejecutar_todo.ps1 -MedirLotes -ProbarPersistencia
```

**Linux o macOS:**

```bash
./scripts/ejecutar_todo.sh                   # perfil local
./scripts/ejecutar_todo.sh muestra
./scripts/ejecutar_todo.sh completo
./scripts/ejecutar_todo.sh local --medir-lotes --probar-persistencia
```

Cada corrida deja su log en `docs/evidencia/logs/ejecucion_<perfil>_<fecha>.log`, con fecha, versión de InfluxDB, recursos y resultados.

| Perfil | Partidos | Captura | Puntos | Series |
| :--- | ---: | ---: | ---: | ---: |
| `muestra` | 2 | 600 s | 22.080 | 72 |
| `local` (por defecto) | 12 | 6.000 s | 1.324.800 | 432 |
| `completo` | 96 | 6.000 s | 10.598.400 | 3.456 |

## Paso a paso (sin el script encadenado)

1. **Preparar y levantar el ambiente.** Crea `~/docker/data/influxdb`, ejecuta `docker compose up -d`, espera al servidor, registra versión y recursos, crea el token local y las tres bases:
   ```bash
   python scripts/inicializacion.py
   ```
   *(En Windows se usa `python`; si no está en el PATH, `py`. Si `HOME` no está definida, `$env:HOME = $env:USERPROFILE`.)*
2. **Comprobar el estado** con las herramientas del contenedor:
   ```bash
   docker compose ps
   docker exec fixture2030-influxdb influxdb3 --version
   ```
3. **Generar los puntos** (no toca InfluxDB):
   ```bash
   python scripts/generacion_puntos.py --perfil local
   ```
4. **Cargar por lotes:**
   ```bash
   python scripts/carga_lotes.py --perfil local
   python scripts/carga_lotes.py --perfil local --tamano-lote 10000 --concurrencia 8   # variantes
   python scripts/carga_lotes.py --perfil local --medir-lotes                          # compara lotes
   ```
5. **Consultar y agregar:**
   ```bash
   python scripts/consultas_temporales.py          # C1 a C7
   python scripts/consultas_temporales.py C2 C5    # solo algunas
   python scripts/agregaciones.py                  # A1 a A7 y el resumen de 1 minuto
   ```
6. **Validar** lo cargado contra lo generado:
   ```bash
   python scripts/validacion.py --perfil local
   ```
7. **Consulta directa con el CLI del contenedor** (ejemplo):
   ```bash
   # Linux/macOS
   export INFLUXDB3_AUTH_TOKEN="$(cat .influxdb3-token)"
   docker exec -e INFLUXDB3_AUTH_TOKEN fixture2030-influxdb influxdb3 query \
     --database fixture2030_vivo "SELECT COUNT(*) AS puntos FROM estadisticas_equipo"
   ```
   ```powershell
   # PowerShell
   $env:INFLUXDB3_AUTH_TOKEN = (Get-Content .influxdb3-token)
   docker exec -e INFLUXDB3_AUTH_TOKEN fixture2030-influxdb influxdb3 query --database fixture2030_vivo "SELECT COUNT(*) AS puntos FROM estadisticas_equipo"
   ```
8. **Detener y reiniciar sin perder datos.** Los datos viven en `~/docker/data/influxdb`:
   ```bash
   docker compose stop       # detiene
   docker compose up -d      # vuelve a iniciar con los mismos datos
   docker compose down       # quita el contenedor; los datos se conservan
   ```
9. **Limpieza opcional** (no es parte del flujo normal):
   ```bash
   python scripts/limpieza.py --generados     # borra data/generado/
   python scripts/limpieza.py --datos --si    # empieza de cero: borra datos y token
   ```

## Verificación de la imagen (RNF1)

El enunciado pide la imagen oficial `influxdb:latest`. El compose usa **`influxdb:3-core`**, también oficial, y la razón es verificable:

- La Clase 9 indica que `latest` apunta a InfluxDB 2.x, que **no incluye el binario `influxdb3`**: un compose con `latest` no puede ejecutar `influxdb3 serve`, ni usar tokens, `query` ni `create database --retention-period`.
- La página oficial de la imagen en Docker Hub lista `latest` junto a la versión 2.9.1 y las etiquetas `3-core` aparte (consultada al preparar esta entrega).

Para comprobarlo en su máquina y dejarlo como evidencia:

```bash
docker pull influxdb:latest
docker run --rm influxdb:latest sh -c "which influxdb3 || echo 'influxdb3 no existe en latest'"
```

Si ese comando llegara a mostrar una ruta, significa que `latest` ya es 3 Core y se puede cambiar `image:` en `docker-compose.yml` a `influxdb:latest` sin tocar nada más. La versión realmente usada queda registrada en el paso 1 de cada log. `pull_policy: always` trae siempre la última versión publicada de la línea.

## Estructura

```
influxdb/
├── docker-compose.yml          # InfluxDB 3 Core, persistencia en ~/docker/data/influxdb
├── .gitignore                  # token, datos generados, caché
├── README.md
├── data/
│   └── origen/                 # CSV del Hito 5 (partidos, equipos, sedes, jugadores, participaciones, eventos)
├── scripts/
│   ├── inicializacion.py       # compose, versión, recursos, bases con su retención
│   ├── autorizacion_local.py   # token de administración local (fuera de Git)
│   ├── generacion_puntos.py    # genera line protocol + manifest (etapa 1)
│   ├── carga_lotes.py          # carga por lotes con concurrencia y reintentos (etapa 2)
│   ├── consultas_temporales.py # ejecuta sql/consultas_temporales.sql
│   ├── agregaciones.py         # ejecuta sql/agregaciones.sql y el resumen de 1 minuto
│   ├── validacion.py           # compara InfluxDB con el manifest (etapa 3)
│   ├── persistencia.py         # cuenta, reinicia el contenedor y vuelve a contar
│   ├── limpieza.py             # limpieza opcional
│   ├── lib_influx.py           # utilidades compartidas
│   ├── ejecutar_todo.ps1       # flujo completo en Windows, con log
│   ├── ejecutar_todo.sh        # flujo completo en Linux/macOS, con log
│   └── sql/
│       ├── consultas_temporales.sql
│       └── agregaciones.sql
└── docs/
    ├── patrones_de_acceso.md          # problema temporal y patrones PA1 a PA6
    ├── modelo_multidimensional.md     # tablas, tags, fields, timestamps, series
    ├── cardinalidad_y_escalabilidad.md# cardinalidad, estrategia de carga y escalabilidad
    ├── carga_y_consultas.md           # etapas, consultas, agregaciones e interpretación
    ├── retencion_y_granularidad.md    # ciclo de vida, retención y resumen
    ├── pruebas_y_evidencia.md         # método, validaciones, resultados y límites
    ├── seguridad_local.md             # token y archivos excluidos
    ├── coherencia_con_el_tpo.md       # relación con los hitos 1 a 7
    └── evidencia/                     # logs de las corridas
```

## Mapa de requisitos

| Requisito | Dónde se cumple |
| :--- | :--- |
| RF1 ambiente y verificación | `docker-compose.yml`; `scripts/inicializacion.py` (versión, `show databases`) |
| RF2 patrones de acceso antes del modelo | `docs/patrones_de_acceso.md` |
| RF3, RF4 modelo y dimensiones | `docs/modelo_multidimensional.md`; `scripts/generacion_puntos.py` |
| RF5 tres o más medidas de distinta naturaleza | `docs/modelo_multidimensional.md` (cuatro naturalezas); `scripts/sql/agregaciones.sql` (A2) |
| RF6 precisión temporal | Segundos: `docs/modelo_multidimensional.md`; `PRECISION` en `scripts/lib_influx.py` |
| RF7 generación, carga y validación separadas | `generacion_puntos.py`, `carga_lotes.py`, `validacion.py` |
| RF8 ventana, comparación de dimensiones | `scripts/sql/consultas_temporales.sql` (C1 a C7) |
| RF9 agregación justificada | `scripts/sql/agregaciones.sql` (A1 a A7) y `agregaciones.py` |
| RF10 retención y granularidad | `docs/retencion_y_granularidad.md`; `inicializacion.py` (`--retention-period`); bloque R1 |
| RF11 cardinalidad | `docs/cardinalidad_y_escalabilidad.md`, sección 1; `validacion.py` (V4) |
| RF12 estrategia 10M+ | `docs/cardinalidad_y_escalabilidad.md`, sección 2; `carga_lotes.py` |
| RF13 prueba de carga y consulta | `docs/pruebas_y_evidencia.md`, sección 4; `carga_lotes.py --medir-lotes` |
| RF14 evidencia | `docs/evidencia/` |
| RNF1 imagen | Sección "Verificación de la imagen" y `docker-compose.yml` |
| RNF2 persistencia | `docker-compose.yml`; paso a paso, punto 8; `scripts/persistencia.py` (con `-ProbarPersistencia`) |
| RNF3 reproducibilidad | Este README |
| RNF4 diseño dirigido por consultas | `docs/modelo_multidimensional.md`, "Relación entre modelo y operaciones" |
| RNF5 cardinalidad | `docs/cardinalidad_y_escalabilidad.md` |
| RNF6 tipos y precisión | `docs/modelo_multidimensional.md`; validación V10 |
| RNF7 seguridad local | `docs/seguridad_local.md`; `.gitignore` |
| RNF8 consultas acotadas, sin afirmaciones sin método | `scripts/sql/*.sql`; `docs/pruebas_y_evidencia.md`, sección 3 |
| RNF9 scripts separados | La carpeta `scripts/` |
| RNF10 evidencia con fecha, versión y recursos | Encabezado de cada log |
| RNF11 repositorio | Este repositorio y su historial |

## Mapa de apartados del análisis

| Apartado | Archivo |
| :--- | :--- |
| Problema temporal; Patrones de acceso | `docs/patrones_de_acceso.md` |
| Modelo multidimensional | `docs/modelo_multidimensional.md` |
| Cardinalidad; Escalabilidad; Carga de datos (estrategia) | `docs/cardinalidad_y_escalabilidad.md` |
| Carga de datos (etapas); Consultas y agregaciones | `docs/carga_y_consultas.md` |
| Retención y granularidad | `docs/retencion_y_granularidad.md` |
| Seguridad local | `docs/seguridad_local.md` |
| Pruebas y evidencia | `docs/pruebas_y_evidencia.md`, `docs/evidencia/` |
| Coherencia con el TPO | `docs/coherencia_con_el_tpo.md` |

## Alcance respecto de lo visto en clase

El módulo usa lo de la Clase 9: tabla, tags, fields, timestamp, serie, line protocol, SQL con `AVG`, `SUM`, `MAX`, `GROUP BY`, retención fijada al crear la base, batching y cardinalidad. Tres elementos van más allá de los ejemplos literales de la clase y se declaran:

- **`date_trunc` y `date_bin`** para las ventanas temporales. La clase explica el concepto de ventana (promedio por minuto, ventanas de 5 minutos) pero no muestra la sintaxis.
- **La API HTTP** (`/api/v3/write_lp` y `/api/v3/query_sql`) como cliente de carga y consulta, que el enunciado admite (RF7: "line protocol, API, CLI o cliente compatible"). El CLI del contenedor se usa para inicializar, crear el token y las bases, y para consultas manuales.
- **Python** para generar y cargar, igual que el Hito 5 usó un generador en Python.

No se usan Flux, InfluxQL, Processing Engine, Telegraf ni Grafana.

## Problemas frecuentes

| Síntoma | Causa y solución |
| :--- | :--- |
| `exec: influxdb3: not found` | Se inició una imagen 2.x. Usar el compose de este repo (`influxdb:3-core`) y `docker compose down`, `docker compose pull`, `docker compose up -d --force-recreate` |
| `PermissionDenied` al crear el catálogo | La imagen no puede escribir en `~/docker/data/influxdb`. En Linux: `sudo chown -R "$(id -u):$(id -g)" ~/docker/data/influxdb` y `sudo chmod -R 777 ~/docker/data/influxdb`, luego `docker compose up -d --force-recreate`. No borrar datos |
| No se pudo crear el token | El servidor ya tenía un token y se perdió `.influxdb3-token`. `python scripts/limpieza.py --datos --si` y volver a inicializar |
| La variable `HOME` no está definida (Windows) | `$env:HOME = $env:USERPROFILE` antes de `docker compose up -d` |
| `failed to connect to the docker API ... dockerDesktopLinuxEngine` | Docker Desktop no está abierto. Abrirlo, esperar a que diga "Engine running" y repetir. `docker version` debe mostrar también la sección Server |
| El script parece colgado, sin salida | Ahora la salida se ve en vivo. Si de todos modos no avanza, en otra ventana: `docker ps`, `docker stats --no-stream` y `docker logs --tail 40 fixture2030-influxdb`. Si el contenedor se reinició por falta de memoria, subir la memoria de Docker (con el backend WSL2, en `%UserProfile%\.wslconfig`) o usar el perfil `muestra` |
| Error de consulta por cantidad de archivos Parquet (perfil `completo`) | Se superó `query-file-limit` (432 por defecto). Subirlo antes de levantar el ambiente: `$env:INFLUXDB3_QUERY_FILE_LIMIT = "5000"` y `docker compose up -d --force-recreate`. Ver `docs/cardinalidad_y_escalabilidad.md` |
| `CARGA ABORTADA: fallaron 5 lotes seguidos` | El servidor cayó a mitad de la carga. Revisar con los comandos de arriba y repetir: la carga es idempotente |
| Carga lenta o lotes rechazados | Ver `data/generado/<perfil>/rechazados.lp` y el mensaje del log. Probar con `--tamano-lote` y `--concurrencia` menores |
