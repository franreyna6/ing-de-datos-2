# Mapa de dependencias — API integrada del Hito 10

**Grupo 8** · Fixture 2030 · Hito 11 (RF1, sección 5.1)

El mapa describe **qué usa la API del Hito 10 tal como está en el repositorio**: el código de
`api/app/adapters/` y la configuración por variables de entorno (`api/app/core/config.py`).
Su versión ejecutable es [`scripts/dependencias.py`](../scripts/dependencias.py): los scripts de
prueba recorren ese mapa en lugar de repetir hosts y puertos.

**Proceso que inicia todas las conexiones:** el proceso `uvicorn app.main:app` de la API,
ejecutado **en la notebook** (Windows 11, Python 3.11 del entorno `api/.venv`). Ningún producto
abre conexiones hacia la API ni hacia otro producto.

## Mapa

| Producto | Módulo del Fixture (hito) | Host:puerto usado desde la API | Protocolo | Contexto (database / keyspace / namespace) | Autenticación (sin valor) | Cliente o driver | Operación mínima evaluada | Endpoint de la API |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| MongoDB 7.0 | Equipos y jugadores (Hito 4) | `localhost:27017` | MongoDB Wire Protocol | database `fixture2030`, colecciones `equipos`, `jugadores` | usuario + password en `MONGODB_URI` (`authSource=admin`) | `pymongo` 4.10 | `hello`, `connectionStatus`, `find_one({codigo})` | `GET /equipos/{codigo}`, `GET /equipos/{codigo}/jugadores` |
| Neo4j 2026.10 Community | Partidos, eventos y participantes (Hito 5) | `localhost:7687` (Bolt) · `localhost:7474` (HTTP, solo Browser) | Bolt 5.x / HTTP | database `neo4j` | `NEO4J_USER` + `NEO4J_PASSWORD` | `neo4j` 5.27 (Bolt) | handshake Bolt, `verify_authentication`, `SHOW DATABASE`, `MATCH` parametrizado | `GET /partidos/{codigo}/eventos` |
| Cassandra 5.0 | Comentarios masivos (Hito 6) | `localhost:9042` | CQL binary protocol v4/v5 | keyspace `fixture2030_comentarios`, tabla `comentarios_por_partido` | ninguna (AllowAllAuthenticator) | `cassandra-driver` 3.29 (si no carga: `cqlsh` vía `docker exec`) | `OPTIONS`/`STARTUP`, `system_schema`, `SELECT … LIMIT` de una partición | `GET`/`POST /partidos/{codigo}/comentarios` |
| Redis 8.10 | Sesiones y caché (Hito 7) | `localhost:6379` | RESP | base lógica 0, claves `sesion:<id>` (hash con TTL) | ninguna (`requirepass` vacío) | `redis-py` 5.2 | `PING`, `DBSIZE`, `TYPE`/`TTL`/`HMGET` de `sesion:S0001` | `GET /sesiones/{sesion_id}` |
| InfluxDB 3 Core 3.12.1 | Estadísticas en vivo (Hito 8) | `127.0.0.1:8181` (recomendado; ver H4) | HTTP API v3 | database `fixture2030_vivo`, tabla `estadisticas_equipo` | token Bearer (`INFLUXDB3_TOKEN`, leído del archivo del Hito 8) | `http.client` (stdlib) → `/api/v3/query_sql` | `/health` sin y con token, catálogo de databases, consulta temporal acotada | `GET /partidos/{codigo}/estadisticas` |
| InterSystems IRIS Community 2026.2 | Entidades complejas (Hito 9) | `127.0.0.1:1972` (Superserver) · `127.0.0.1:52773` (Portal, no lo usa la API) | protocolo propio del Superserver / HTTP | namespace `USER`, esquema SQL `Fixture` | `IRIS_USER` + `IRIS_PASSWORD` | `intersystems-irispython` 5.4 (DB-API) | conexión al namespace, `INFORMATION_SCHEMA`, `SELECT … FROM Fixture.Partido` | `GET /partidos/{codigo}/detalle` |

Las versiones son las **observadas** en la corrida final (no supuestas): salen de las propias
respuestas de cada producto (`hello`, discovery HTTP de Neo4j, `system.local`, `INFO server`,
`influxdb3 --version`, `$ZVERSION`). Ver [`evidencia/corridas/`](evidencia/corridas/).

## Variables de configuración por producto

Los nombres son **los mismos** que lee la API (`api/.env.example`), para que la evaluación pruebe
exactamente la configuración de la aplicación. Los valores de ejemplo, sin secretos, están en
[`config/configuracion-ejemplo.env`](../config/configuracion-ejemplo.env).

| Producto | Variables obligatorias | Variables opcionales / de la evaluación |
| :--- | :--- | :--- |
| MongoDB | `MONGODB_URI`, `MONGODB_DATABASE` | `MONGO_CONTAINER` |
| Neo4j | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` | `NEO4J_DATABASE`, `NEO4J_HTTP_URL`, `NEO4J_CONTAINER` |
| Cassandra | `CASSANDRA_HOST`, `CASSANDRA_PORT`, `CASSANDRA_KEYSPACE` | `CASSANDRA_CONTAINER` (alternativa `cqlsh` de la API) |
| Redis | `REDIS_URL` | `REDIS_CONTAINER` |
| InfluxDB | `INFLUX_URL`, `INFLUX_DATABASE`, `INFLUXDB3_TOKEN` | `INFLUXDB3_TOKEN_FILE` (solo la evaluación), `INFLUX_CONTAINER` |
| IRIS | `IRIS_HOST`, `IRIS_PORT`, `IRIS_NAMESPACE`, `IRIS_USER`, `IRIS_PASSWORD` | `IRIS_PORTAL_URL`, `IRIS_CONTAINER` |
| API | — | `API_BASE_URL`, `DEP_TIMEOUT_S` (timeout de la API), `TIMEOUT_S` (timeout de la evaluación) |

## Estado esperado y estado observado

“Esperado” es lo que el contrato del Hito 10 promete; “observado” es el resultado de la
**corrida final** (`evidencia/corridas/20261023_032545_final/`, commit `b6d4e88`). El detalle,
la latencia y el diagnóstico están en [`matriz_de_conectividad.md`](matriz_de_conectividad.md).

| Producto | Estado esperado | Estado observado (corrida final) | Motivo |
| :--- | :--- | :--- | :--- |
| MongoDB | disponible | **degradado** | el producto responde en todas las capas; la API consulta por `_id` y el Hito 4 guarda el código en `codigo` (H1) |
| Neo4j | disponible | **disponible** | todas las capas y las 3 rutas según el contrato |
| Cassandra | disponible | **disponible** | todas las capas y las 3 rutas según el contrato |
| Redis | disponible | **degradado** | el producto responde; la API lee con `GET` una sesión que el Hito 7 guarda como hash (H2) |
| InfluxDB | disponible | **degradado** | el producto responde con token y database; la API envía el campo `query` en lugar de `q` (H6) |
| IRIS | disponible | **degradado** | el producto responde tras corregir la credencial (C1); el SQL de la API usa el alias reservado `local` (H7) |

Ningún producto está en `no_probado` ni `desconocido`: todas las herramientas necesarias
estuvieron disponibles (0 pruebas SKIP). Los estados `no_configurado` y `desconocido` se
conservan en el procedimiento y aparecen si falta una variable o un driver (ver
[`capas_de_evaluacion.md`](capas_de_evaluacion.md)).
