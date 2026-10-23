# Pruebas nativas y pruebas de la API

**Grupo 8** · Fixture 2030 · Hito 11 (RF6–RF15, RF19, secciones 5.4 y 5.5)

Resultados de la **corrida final** (`evidencia/corridas/20261023_032545_final/`, 2026-10-23
06:26 UTC, commit `b6d4e88`), salvo que se indique otra cosa.

## 1. Pruebas nativas

### Desde la notebook (mismo origen y mismos drivers que la API)

`scripts/prueba_clientes_nativos.py`. El detalle de cada prueba, su pregunta y lo que no permite
concluir está en [`capas_de_evaluacion.md`](capas_de_evaluacion.md).

| Producto | Cliente | Contexto | Lectura mínima | Resultado |
| :--- | :--- | :--- | :--- | :--- |
| MongoDB | `pymongo` 4.10 | `fixture2030` | `find_one({codigo:'ARG'}, proyección)` · `count_documents({equipoCodigo:'ARG'}, limit=100)` | Argentina, CONMEBOL · 16 jugadores |
| Neo4j | `neo4j` 5.27 (Bolt 5.8) | `neo4j` | `MATCH (p:Partido {codigo:$codigo}) OPTIONAL MATCH (e:Evento)-[:OCURRE_EN]->(p) … LIMIT 1` | F2030-001, 2030-06-14, 2 eventos |
| Cassandra | `cassandra-driver` 3.29 | `fixture2030_comentarios` | `SELECT … WHERE partido_id=? AND ventana=? LIMIT 5` (prepared) | 2 filas de la partición (F2030-063, 20:00Z) |
| Redis | `redis-py` 5.2 | base 0 | `TYPE` / `TTL` / `HMGET usuario_id estado` de `sesion:S0001` | hash, TTL 424 s, U0001, activa |
| InfluxDB | HTTP `/api/v3/query_sql` | `fixture2030_vivo` | `COUNT`, `AVG(posesion_pct)`, `MAX(pases_acum)` de F2030-018 en `[08:00, 08:05)` agrupado por equipo | ALG y TUN: 300 puntos cada uno, posesión ~50 % |
| IRIS | `intersystems-irispython` 5.4 | `USER` / `Fixture` | `SELECT Codigo, Estado, GolesLocal, GolesVisitante FROM Fixture.Partido WHERE Codigo = ?` | F2030-001, Finalizado, 1-1 |

### Dentro de cada contenedor (cliente nativo del producto)

Comandos exactos que ejecuta el script. Las credenciales viajan como **variables de entorno**
del `docker exec` (`-e NOMBRE`, sin valor en la línea de comandos), nunca como argumentos.

```bash
# MongoDB: mongosh lee usuario y password de process.env
docker exec -e H11_U -e H11_P -e H11_DB -e H11_EQ fixture2030-mongodb \
  mongosh --quiet --nodb --eval "const c = connect('mongodb://'+…+'@localhost:27017/'+process.env.H11_DB+'?authSource=admin'); …findOne({codigo: process.env.H11_EQ})…"

# Neo4j: cypher-shell toma NEO4J_USERNAME / NEO4J_PASSWORD del entorno
docker exec -e NEO4J_USERNAME -e NEO4J_PASSWORD fixture2030-neo4j \
  cypher-shell -a bolt://localhost:7687 -d neo4j --format plain -P "{codigo: 'F2030-001'}" \
  "MATCH (p:Partido {codigo: \$codigo}) OPTIONAL MATCH (e:Evento)-[:OCURRE_EN]->(p) RETURN p.codigo AS partido, count(e) AS eventos LIMIT 1"

# Cassandra
docker exec fixture2030-cassandra cqlsh -k fixture2030_comentarios -e \
  "SELECT partido_id, ventana, creado_en FROM comentarios_por_partido WHERE partido_id = 'F2030-063' AND ventana = '2030-06-22 20:00:00+0000' LIMIT 3"

# Redis
docker exec fixture2030-redis sh -c "redis-cli PING; redis-cli TYPE sesion:S0001; redis-cli TTL sesion:S0001; redis-cli INFO server | grep redis_version"

# InfluxDB: el CLI lee INFLUXDB3_AUTH_TOKEN del entorno
docker exec -e INFLUXDB3_AUTH_TOKEN fixture2030-influxdb influxdb3 query --database fixture2030_vivo \
  "SELECT COUNT(*) AS puntos FROM estadisticas_equipo WHERE partido_id = 'F2030-018' AND time >= '2030-06-13T08:00:00Z' AND time < '2030-06-13T08:05:00Z'"

# IRIS: Terminal (autenticación del sistema operativo del contenedor)
printf 'Write "NS=",$NAMESPACE," EXISTE=",##class(Fixture.Partido).CodigoIdxExists("F2030-001"),!\nHalt\n' \
  | docker exec -i fixture2030-iris iris session IRIS -U USER
```

| Producto | Salida observada (redactada) | ms |
| :--- | :--- | ---: |
| MongoDB | `{"ping":1,"version":"7.0.45","db":"fixture2030","equipos":64,"equipo":{"codigo":"ARG","nombre":"Argentina"}}` | 543 |
| Neo4j | `partido, eventos \| "F2030-001", 2` | 1.772 |
| Cassandra | `(2 rows)` | 515 |
| Redis | `PONG \| hash \| 423 \| redis_version:8.10.2` | 181 |
| InfluxDB | `puntos=600 \| influxdb3 InfluxDB 3 Core, 3.12.1` | 196 |
| IRIS | `NS=USER EXISTE=1 \| VERSION=IRIS for UNIX … 2026.2 (Build 221U)` | 102 |

Los tiempos incluyen el arranque de cada CLI dentro del contenedor (sobre todo la JVM de
`cypher-shell`): no se comparan con los del driver.

## 2. Pruebas de la API (cadena cliente HTTP → API → adaptador → producto)

`scripts/prueba_api.py` levanta la API del Hito 10 **sin modificarla** (`uvicorn app.main:app`
en `127.0.0.1`, primer puerto libre desde 8000), envía cada request con su propio
`X-Request-ID` y busca ese id en el log de la API. La categoría esperada se declara **antes** de
probar, según el contrato del Hito 10. Solo rutas de lectura (RNF6).

Log completo redactado: [`evidencia/corridas/20261023_032545_final/api_redactado.log`](evidencia/corridas/20261023_032545_final/api_redactado.log).

| Dependencia | Método y path (parámetros) | HTTP | Categoría observada | Esperada | Resultado | ms | Request ID | Log asociado |
| :--- | :--- | :---: | :--- | :--- | :---: | ---: | :--- | :--- |
| — | `GET /salud` en un puerto sin API | — | api_no_alcanzable | api_no_alcanzable | OK | 2.046 | — | — (`connection refused`) |
| todas | `GET /salud` | 200 | (6 booleanos) | — | INFO | 2.188 | `h11-final-salud-73c1` | `influx status=400` / `GET /salud -> 200 (2172.1 ms)` |
| MongoDB | `GET /equipos/ARG` | 404 | recurso_inexistente | exito | **FALLA** | 3 | `h11-final-01-8fa9` | `mongo equipo codigo=ARG encontrado=False` (H1) |
| MongoDB | `GET /equipos/ZZZ` | 404 | recurso_inexistente | recurso_inexistente | OK | 17 | `h11-final-02-e856` | `mongo equipo codigo=ZZZ encontrado=False` |
| MongoDB | `GET /equipos/ARG/jugadores?limit=5` | 500 | error_interno | exito | **FALLA** | 29 | (sin header, H8) | `mongo jugadores equipo=ARG filas=5` / `error inesperado … ResponseValidationError()` |
| MongoDB | `GET /equipos/ARG/jugadores?limit=0` | 400 | error_validacion | error_validacion | OK | 3 | `h11-final-04-e6fa` | `GET /equipos/ARG/jugadores -> 400 (1.5 ms)` (no consultó la base) |
| Neo4j | `GET /partidos/F2030-001/eventos?limit=5` | 200 | exito | exito | OK | 10 | `h11-final-05-d217` | `neo4j partido=F2030-001 eventos=2` |
| Neo4j | `GET /partidos/F2030-006/eventos?limit=5` | 200 | vacio_valido | vacio_valido | OK | 8 | `h11-final-06-0457` | `neo4j partido=F2030-006 eventos=0` |
| Neo4j | `GET /partidos/F2030-999/eventos` | 404 | recurso_inexistente | recurso_inexistente | OK | 35 | `h11-final-07-87c7` | `neo4j partido=F2030-999 inexistente` |
| Cassandra | `GET /partidos/F2030-063/comentarios?instante=2030-06-22T20:03:00Z&limit=5` | 200 | exito | exito | OK | 14 | `h11-final-08-cc60` | `cassandra leer … ventana=2030-06-22 20:00:00+00:00 filas=2 modo=driver` |
| Cassandra | `…/comentarios?instante=2029-06-22T20:03:00Z&limit=5` | 200 | vacio_valido | vacio_valido | OK | 15 | `h11-final-09-442e` | `… filas=0 modo=driver` |
| Cassandra | `…/comentarios?instante=no-es-fecha` | 400 | error_validacion | error_validacion | OK | 2 | `h11-final-10-adf8` | `-> 400 (0.6 ms)` |
| Redis | `GET /sesiones/S0001` | 503 | dependencia_no_disponible | exito | **FALLA** | 3 | `h11-final-11-41b3` | `causa=WRONGTYPE Operation against a key holding the wrong kind of value` (H2) |
| Redis | `GET /sesiones/no-existe-h11` | 404 | recurso_inexistente | recurso_inexistente | OK | 2 | `h11-final-12-21a5` | `redis sesion=no-existe-h11 ausente_o_expirada` |
| InfluxDB | `GET /partidos/F2030-018/estadisticas?desde=…08:00:00Z&hasta=…08:05:00Z` | 503 | dependencia_no_disponible | exito | **FALLA** | 4 | `h11-final-13-8088` | `influx status=400` / `causa=HTTP 400` (H6) |
| InfluxDB | `…/estadisticas?desde=…09:00:00Z&hasta=…09:15:00Z` | 503 | dependencia_no_disponible | vacio_valido | **FALLA** | 4 | `h11-final-14-ebcf` | `causa=HTTP 400` (H6) |
| InfluxDB | `…/estadisticas` con `desde > hasta` | 400 | error_validacion | error_validacion | OK | 2 | `h11-final-15-7523` | `-> 400 (0.5 ms)` |
| IRIS | `GET /partidos/F2030-001/detalle` | 503 | dependencia_no_disponible | exito | **FALLA** | 9 | `h11-final-16-8d2d` | `causa=<SQL ERROR> … [SQLCODE: <-1>:<Invalid SQL statement>]` (H7) |
| IRIS | `GET /partidos/F2030-999/detalle` | 503 | dependencia_no_disponible | recurso_inexistente | **FALLA** | 5 | `h11-final-17-189f` | ídem (H7) |

### Las seis situaciones de la sección 5.5, observadas

| Situación | Caso que la muestra |
| :--- | :--- |
| API no alcanzable | `/salud` en un puerto sin proceso → sin respuesta HTTP (`connection refused`) |
| API alcanzable con dependencia fallida | Redis detenido (falla controlada) → `503` en `/sesiones`, y `200` en Neo4j |
| Recurso inexistente | `/equipos/ZZZ`, `/partidos/F2030-999/eventos`, `/sesiones/no-existe-h11` → `404` |
| Respuesta vacía válida | `/partidos/F2030-006/eventos` y comentarios de 2029 → `200` con lista vacía |
| Error de validación | `limit=0`, `instante=no-es-fecha`, `desde > hasta` → `400` sin consultar la base |
| Operación exitosa | eventos de F2030-001 (Neo4j) y comentarios de F2030-063 (Cassandra) → `200` |

### Correlación request ↔ log (RF19, RNF11)

Cada línea del log de la API tiene `[req=<id>]`. El id que envía la evaluación vuelve en el
header `X-Request-ID` y aparece en todas las líneas del adaptador y en la línea de acceso
(`método ruta -> status (ms)`). Por eso cada fila de la tabla anterior se puede rastrear hasta su
causa técnica, que **solo** está en el log (el cliente recibe el error de dominio).
Excepción: los 500 (H8).
