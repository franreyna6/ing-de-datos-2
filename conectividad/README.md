# Hito 11 — Evaluación de la conectividad a los productos del Fixture 2030

**Repositorio del grupo:** https://github.com/franreyna6/ing-de-datos-2 (carpeta `conectividad/`)

Ingeniería de Datos II · Grupo 8 · Fixture Mundial 2030 · Clase 12

Procedimiento reproducible para evaluar, **capa por capa**, si la API integrada del Hito 10
([`api/`](../api/)) puede localizar, alcanzar, autenticar y usar cada uno de sus seis productos:
MongoDB, Neo4j, Cassandra, Redis, InfluxDB e IRIS. Las capas son configuración → resolución →
TCP → protocolo → autenticación → autorización → contexto → lectura mínima → endpoint de la API.
Cada producto se prueba con su cliente, driver o protocolo propio, desde el mismo entorno en el que
corre la API. El procedimiento provoca fallas controladas sin borrar datos y produce una matriz
de estados con su evidencia redactada.

> **Resultado en una línea (corrida final, 2026-10-23):** los seis productos responden por su
> cliente nativo. Neo4j y Cassandra están `disponible` de punta a punta. MongoDB, Redis, InfluxDB
> e IRIS están `degradado`: el producto funciona, pero la operación que ejecuta la API no
> coincide con el modelo o con el protocolo del producto (H1, H2, H6, H7). Tres fallas de entorno
> se corrigieron con antes y después (C1, C2, C3), sin tocar la API. Ver
> [`docs/matriz_de_conectividad.md`](docs/matriz_de_conectividad.md).

## Requisitos

- **Docker Desktop** (o Docker Engine) con `docker compose`. Los clientes nativos (`mongosh`,
  `cypher-shell`, `cqlsh`, `redis-cli`, `influxdb3`, `iris session`) se usan **dentro** de cada
  contenedor: no hace falta instalarlos en la notebook.
- **Python 3.11** con el entorno de la API (`api/.venv`), que tiene los mismos drivers que la API.
  Con Python 3.12 o superior, `cassandra-driver` no carga: esas pruebas quedan en SKIP.
- Las bases de los hitos 4 a 9 levantadas con **su propio** `docker-compose.yml` (ver
  preparación). No hace falta tenerlas todas a la vez: lo que no esté disponible se informa como
  tal (RNF13).

## Variables

Se usan **los mismos nombres que la API**. Plantilla sin secretos:
[`config/configuracion-ejemplo.env`](config/configuracion-ejemplo.env). La copia local
`config/configuracion.env` está excluida de Git. Prioridad: variable de entorno →
`configuracion.env` → valor por defecto (los valores por defecto no incluyen credenciales).

| Grupo | Variables |
| :--- | :--- |
| MongoDB | `MONGODB_URI` (con usuario y password), `MONGODB_DATABASE` |
| Neo4j | `NEO4J_URI`, `NEO4J_HTTP_URL`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` |
| Cassandra | `CASSANDRA_HOST`, `CASSANDRA_PORT`, `CASSANDRA_KEYSPACE` |
| Redis | `REDIS_URL` |
| InfluxDB | `INFLUX_URL`, `INFLUX_DATABASE`, `INFLUXDB3_TOKEN_FILE` (o `INFLUXDB3_TOKEN`) |
| IRIS | `IRIS_HOST`, `IRIS_PORT`, `IRIS_PORTAL_URL`, `IRIS_NAMESPACE`, `IRIS_USER`, `IRIS_PASSWORD` |
| Evaluación | `TIMEOUT_S` (3,0), `API_BASE_URL`, `*_CONTAINER`, `PRUEBA_*` (datos de prueba) |

Detalle y diferencias notebook/contenedor: [`docs/topologia_y_entornos.md`](docs/topologia_y_entornos.md) §5.

## Preparación (una vez)

Desde la raíz del repositorio. En Windows, antes de los `compose` que usan `${HOME}`:
`$env:HOME = $env:USERPROFILE`.

1. **Entorno de la API** (Python 3.11):
   ```powershell
   cd api
   py -3.11 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt intersystems-irispython
   ```
   (Linux/macOS: `python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt intersystems-irispython`.)

2. **Levantar y cargar cada base con los scripts de su hito** (lecturas de laboratorio propias):

   | Hito | Levantar | Cargar datos |
   | :--- | :--- | :--- |
   | 4 MongoDB | `docker compose up -d mongodb` en la carpeta entregada del Hito 4 | `docker exec fixture2030-mongodb mongosh -u <usuario> -p <password> --authenticationDatabase admin fixture2030 --file /scripts/01-cargar-datos.js` (y `02-crear-indices.js`) |
   | 5 Neo4j | `cd neo4j && docker compose up -d` | `Get-Content queries\estructura.cypher, queries\carga.cypher \| docker exec -i fixture2030-neo4j cypher-shell -u neo4j -p <password>` |
   | 6 Cassandra | `cd cassandra && docker compose up -d` | `docker exec fixture2030-cassandra cqlsh -f /scripts/esquema.cql` y `… -f /scripts/carga_muestra.cql` |
   | 7 Redis | `cd redis && docker compose up -d` | `docker exec fixture2030-redis sh /scripts/ejecutar_bloques.sh /scripts/carga_muestra.redis carga` (las sesiones vencen a los 30 min: repetir antes de evaluar) |
   | 8 InfluxDB | `cd influxdb && python scripts/inicializacion.py` | `python scripts/generacion_puntos.py --perfil muestra` y `python scripts/carga_lotes.py --perfil muestra` |
   | 9 IRIS | `cd iris && docker compose -f docker-compose.yml -f docker-compose.windows.yml up -d` | Terminal: `$system.OBJ.LoadDir("/iris/src","ck",.err,1)` y `Do ##class(Fixture.Demo).Bloque1Carga()` (ver README del Hito 9) |

   En Git Bash, anteponer `MSYS_NO_PATHCONV=1` a los `docker exec` con rutas `/scripts/…`.

   - **Token de InfluxDB perdido** (el servidor tiene uno y falta `influxdb/.influxdb3-token`):
     **no** borrar datos. Seguir el procedimiento de recuperación de
     [`docs/evidencia/diagnostico/C0_influx_token_recuperado.txt`](docs/evidencia/diagnostico/C0_influx_token_recuperado.txt).
   - **IRIS Community exige cambiar la password predeterminada** (si no, el driver responde
     *Password change required*, hallazgo H3). Definir una password local propia, sin
     publicarla:
     ```bash
     printf 'Set p("Password")="<password local>",p("ChangePassword")=0\nWrite ##class(Security.Users).Modify("_SYSTEM",.p),!\nHalt\n' \
       | docker exec -i fixture2030-iris iris session IRIS -U %SYS        # debe imprimir 1
     ```

3. **Configuración de la evaluación:**
   ```bash
   cd conectividad
   cp config/configuracion-ejemplo.env config/configuracion.env    # PowerShell: Copy-Item
   # completar los <...> con las credenciales de laboratorio de cada hito y la password local de IRIS
   ```

## Orden de ejecución

Desde `conectividad/`. En Windows: `.\scripts\evaluar_conectividad.ps1 …`; en Linux, macOS o
Git Bash: `./scripts/evaluar_conectividad.sh …`. Ambos usan el Python de `api/.venv`.

| Paso | Comando | Qué hace |
| :---: | :--- | :--- |
| 1 | `… --modo configuracion` | Capa 1: variables (sin mostrar secretos), drivers, Docker, contenedores |
| 2 | `… --modo tcp` | Capas 2 y 3 + tipos de falla TCP (tabla 5.3) + vista desde un contenedor |
| 3 | `… --modo nativos` | Capas 4 a 8 con driver (notebook) y CLI (contenedor), con casos negativos |
| 4 | `… --modo api --iniciar-api` | Capa 9: levanta la API del Hito 10 sin modificarla, prueba sus rutas y cruza el request ID con el log |
| — | `… --modo completo --iniciar-api --etiqueta <nombre>` | Los cuatro anteriores en orden + matriz |
| 5 | `… falla` | Fallas controladas: Redis detenido y recuperado, timeout bajo, token ausente |

- **Por producto:** `--producto redis,neo4j` en cualquier modo (RNF13).
- **API ya iniciada:** sin `--iniciar-api` se usa `API_BASE_URL`. Si no responde, se informa
  “API no alcanzable” y no se ejecutan las rutas.
- **Salidas:** `docs/evidencia/corridas/<fecha>_<etiqueta>/` (`resultados_*.txt|json`,
  `matriz.md`, `api_redactado.log`), una copia de la última corrida en `docs/evidencia/`, y el
  resumen de estados en la consola.

### Cómo leer el resumen

- **OK:** esa prueba concreta funcionó en ese momento. No garantiza rendimiento ni disponibilidad permanente.
- **FALLA:** la prueba se intentó y no dio lo esperado. El detalle dice la capa y la causa.
- **SKIP:** la prueba **no se ejecutó** por falta de herramienta o configuración (sin Docker, sin
  driver, sin token). **No significa producto caído.**
- **INFO:** dato de contexto que no decide el estado (por ejemplo, “contenedor running”).
- Estados por dependencia: `disponible`, `degradado`, `no_disponible`, `no_configurado`,
  `desconocido`, `no_probado` ([`docs/matriz_de_conectividad.md`](docs/matriz_de_conectividad.md)).

## Limpieza (opcional)

```bash
python scripts/limpieza.py            # lista lo que borraría
python scripts/limpieza.py --si       # borra logs crudos locales y __pycache__
```

No toca contenedores, volúmenes ni datos. Para detener las bases sin perder datos, usar
`docker compose stop` en la carpeta de cada hito. **Nunca** `down -v`.

## Estructura

```
conectividad/
├── README.md
├── .gitignore                         # configuracion.env, tokens, logs crudos
├── config/
│   ├── configuracion-ejemplo.env      # variables sin secretos (mismos nombres que la API)
│   └── .gitignore                     # solo se versiona el ejemplo
├── scripts/
│   ├── evaluar_conectividad.py|.ps1|.sh  # orquestador: modos, resumen y matriz
│   ├── prueba_configuracion.py        # capa 1
│   ├── prueba_tcp.py                  # capas 2-3, tabla 5.3, vista desde un contenedor
│   ├── prueba_clientes_nativos.py     # capas 4-8 por producto (driver y CLI)
│   ├── prueba_api.py                  # capa 9: rutas del Hito 10 con request ID y log
│   ├── falla_controlada.py            # escenarios reversibles de falla y recuperación
│   ├── dependencias.py                # mapa de dependencias ejecutable
│   ├── api_local.py                   # inicia/detiene la API del Hito 10 y captura su log
│   ├── lib_conectividad.py            # config, redacción, TCP, HTTP, docker exec, evidencia
│   └── limpieza.py                    # opcional, solo archivos locales
└── docs/
    ├── mapa_de_dependencias.md
    ├── topologia_y_entornos.md
    ├── capas_de_evaluacion.md
    ├── matriz_de_conectividad.md
    ├── pruebas_nativas_y_api.md
    ├── diagnostico_de_fallas.md
    ├── health_readiness.md
    ├── limitaciones_y_coherencia.md
    └── evidencia/                     # resultados_*, corridas/, falla_controlada/, diagnostico/
```

## Mapa de requisitos

| Requisito | Dónde |
| :--- | :--- |
| RF1 dependencias | `docs/mapa_de_dependencias.md`, `scripts/dependencias.py` |
| RF2 topología | `docs/topologia_y_entornos.md` |
| RF3 configuración sin secretos | `scripts/prueba_configuracion.py`, `config/configuracion-ejemplo.env` |
| RF4 resolución | `scripts/prueba_tcp.py` (desde la notebook y desde un contenedor) |
| RF5 TCP | `scripts/prueba_tcp.py`, `docs/capas_de_evaluacion.md` (tabla 5.3) |
| RF6 handshake | `prueba_clientes_nativos.py`: `hello`, Bolt, CQL `OPTIONS`, RESP, `/health`, Portal |
| RF7 identidad y contexto | `prueba_clientes_nativos.py` (capas autenticación, autorización, contexto) |
| RF8 operación mínima no destructiva | lecturas acotadas en `prueba_clientes_nativos.py` |
| RF9–RF14 por producto | `prueba_clientes_nativos.py`, `docs/capas_de_evaluacion.md` |
| RF15 rutas de la API | `scripts/prueba_api.py`, `docs/pruebas_nativas_y_api.md` §2 |
| RF16 matriz | `docs/matriz_de_conectividad.md`, `docs/evidencia/corridas/*/matriz.md` |
| RF17, RF18 comportamiento ante fallas | `docs/diagnostico_de_fallas.md` §3–§4, `docs/health_readiness.md` |
| RF19 request ID, duración, resultado | `prueba_api.py` (`X-Request-ID` propio + log), `api_redactado.log` |
| RF20 repetición tras corregir | C1, C2, C3 en `docs/diagnostico_de_fallas.md`; `evidencia/diagnostico/`, `evidencia/corridas/` |
| RF21 detención temporal | `scripts/falla_controlada.py` (`redis_detenido`), `docs/diagnostico_de_fallas.md` §2 |
| RF22, RNF16 GitHub | este repositorio, commits “Hito 11: …” |
| RNF1 reproducibilidad | este README |
| RNF2 capas | `docs/capas_de_evaluacion.md` |
| RNF3 entorno correcto | origen `notebook`/`contenedor` en cada resultado; `docs/topologia_y_entornos.md` §3 |
| RNF4 clientes adecuados | un cliente por producto; `curl` no se usa con Bolt, CQL ni RESP |
| RNF5 timeouts | `TIMEOUT_S` en toda operación; `docker exec` y HTTP con límite |
| RNF6 no destructivo | solo lecturas, pings y `RETURN 1`; la falla usa `stop`/`start` |
| RNF7, RNF8 secretos | `.gitignore`, `redactar()`, `docs/evidencia/README.md` |
| RNF9 estados | `evaluar_conectividad.py` (`estado_dependencia`), `docs/matriz_de_conectividad.md` |
| RNF10 diagnóstico | `docs/diagnostico_de_fallas.md` (hipótesis, prueba, resultado, siguiente paso) |
| RNF11 observabilidad | request ID por prueba, líneas de log correlacionadas en los JSON |
| RNF12 degradación | `docs/diagnostico_de_fallas.md` §4 |
| RNF13 independencia | `--modo` y `--producto` |
| RNF14 integridad del contexto | cada resultado guarda su `objetivo` (database, keyspace, clave, ventana) |
| RNF15 legibilidad | un script por capa, `limpieza.py` aparte |
| RNF17 honestidad | significado de OK y SKIP en el resumen y en la matriz |
| RNF18 trazabilidad | encabezado de cada `resultados_*.txt` y campos `fecha`/`commit` en los JSON |

## Mapa de apartados del análisis (sección 8)

| Apartado | Archivo |
| :--- | :--- |
| Mapa de dependencias | `docs/mapa_de_dependencias.md` |
| Topología | `docs/topologia_y_entornos.md` §1–§4 |
| Capas de evaluación | `docs/capas_de_evaluacion.md` |
| Matriz de conectividad | `docs/matriz_de_conectividad.md` |
| Pruebas nativas | `docs/pruebas_nativas_y_api.md` §1, `docs/capas_de_evaluacion.md` |
| Pruebas de API | `docs/pruebas_nativas_y_api.md` §2 |
| Fallo controlado | `docs/diagnostico_de_fallas.md` §2–§3 |
| Health y readiness | `docs/health_readiness.md` |
| Configuración | `docs/topologia_y_entornos.md` §5, `config/configuracion-ejemplo.env` |
| Evidencia | `docs/evidencia/README.md` |
| Limitaciones | `docs/limitaciones_y_coherencia.md` §1 |
| Coherencia con el TPO | `docs/limitaciones_y_coherencia.md` §2 |
