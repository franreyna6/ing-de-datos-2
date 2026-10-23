# Matriz de conectividad — corrida `inicial`

- **Fecha (UTC):** 2026-10-23T06:18:20Z
- **Commit:** `c2502d1+cambios_locales`
- **Entorno de ejecución:** notebook Windows 10 | Python 3.11.9 (.venv) — mismo origen que la API del Hito 10
- **Docker:** Docker Engine 29.8.2
- **Modo:** `completo` · **timeout por operación:** 3.0 s
- **Significado:** OK = esa prueba concreta funcionó en este momento; no garantiza rendimiento ni disponibilidad permanente (RNF17). SKIP = no se ejecutó por falta de herramienta o configuración, no producto caído.

## Estado por dependencia

| Dependencia | Host:puerto (desde la API) | Contexto | Estado | Capa con falla | OK/FALLA/SKIP | Rutas API según contrato | Diagnóstico automático |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| **mongodb** | `localhost:27017` (MongoDB Wire Protocol (OP_MSG)) | database fixture2030 / colecciones equipos, jugadores | **degradado** | api | 16/3/0 | 2/4 | Consulta identica al adaptador de la API {_id: 'ARG'}: sin resultados: en los datos del Hito 4 el _id es un ObjectId y el codigo FIFA esta en el campo 'codigo'. El clien… |
| **neo4j** | `localhost:7687` (Bolt) | database neo4j | **disponible** | - | 20/0/0 | 3/3 | todas las pruebas positivas OK |
| **cassandra** | `localhost:9042` (CQL binary protocol (v4/v5)) | keyspace fixture2030_comentarios / tabla comentarios_por_partido | **disponible** | - | 20/0/0 | 3/3 | todas las pruebas positivas OK |
| **redis** | `localhost:6379` (RESP) | base logica 0 / claves sesion:<id> | **degradado** | api | 12/2/0 | 1/2 | Operacion identica al adaptador de la API: GET sesion:S0001: ResponseError: WRONGTYPE Operation against a key holding the wrong kind of value: el Hito 7 guarda la sesion… |
| **influxdb** | `localhost:8181` (HTTP (API v3)) | database fixture2030_vivo / tabla estadisticas_equipo | **degradado** | api | 14/2/0 | 1/3 | GET /partidos/F2030-018/estadisticas?desde=2030-06-13T08%3A00%3A00Z&hasta=2030-06-13T08%3A05%3A00Z: HTTP 503 dependencia_no_disponible / DEPENDENCY_UNAVAILABLE: La fuent… |
| **iris** | `localhost:1972` (IRIS Superserver (protocolo propio)) | namespace USER / esquema SQL Fixture | **no_disponible** | autenticacion | 9/3/0 | 0/2 | Conexion al Superserver como '_SYSTEM' en 'USER': Superserver responde y la identidad existe, pero la password esta EXPIRADA (IRIS Community exige cambiarla en el primer… |

## mongodb

| Capa | Prueba | Origen | Cliente | Resultado | ms | Detalle |
| :--- | :--- | :--- | :--- | :---: | ---: | :--- |
| configuracion | Variables de conexion completas y validas | notebook | lectura de configuracion | OK | - | MONGODB_URI=mongodb://admin:****@localhost:27017/?authSource=admin [con credencial (oculta)] [configuracion.env]; MONGODB_DATABASE=fixture2030 [configuracion.env] |
| configuracion | Driver de la API importable en este Python | notebook | pymongo | OK | - | pymongo 4.10.1 |
| configuracion | Estado del contenedor (informativo) | notebook | docker inspect | INFO | - | fixture2030-mongodb: running |
| resolucion | Resolver host (driver de la API) | notebook | socket.getaddrinfo | OK | - | localhost -> 127.0.0.1, ::1 |
| tcp | Conexion TCP (driver de la API) | notebook | socket.create_connection | OK | 1 | exito: conexion establecida ::1 -> ::1:27017 |
| tcp | TCP por familia de direcciones (driver de la API) | notebook | socket.create_connection | INFO | - | 127.0.0.1 -> exito (0 ms); ::1 -> exito (0 ms) |
| protocolo | Handshake del Wire Protocol (comando hello, sin credencial) | notebook | pymongo | OK | 30 | maxWireVersion=21 primario=True |
| autenticacion | Identidad configurada autentica (connectionStatus) | notebook | pymongo | OK | 40 | autenticado como admin@admin |
| autenticacion | [negativo] Password invalida | notebook | pymongo | OK | 34 | rechazada: OperationFailure: Authentication failed., full error: {'ok': 0.0, 'errmsg': 'Authentication failed.', 'code': 18, 'codeName': 'AuthenticationFailed'} (code 18) |
| autorizacion | Permiso de lectura de catalogo en 'fixture2030' | notebook | pymongo | OK | 1 | colecciones: equipos, jugadores |
| contexto | Database 'fixture2030' existe con las colecciones del modulo | notebook | pymongo | OK | 1 | database y colecciones equipos/jugadores presentes |
| contexto | [negativo] Database inexistente | notebook | pymongo | OK | 1 | MongoDB NO devuelve error: la lectura vuelve vacia (None). Solo el catalogo (listDatabases) revela que la database no existe |
| lectura | Lectura de equipo por codigo de negocio {codigo: 'ARG'} | notebook | pymongo | OK | 1 | {"codigo": "ARG", "confederacion": "CONMEBOL", "nombre": "Argentina"} |
| lectura | Conteo acotado de jugadores {equipoCodigo: 'ARG'} (limit 100) | notebook | pymongo | OK | 1 | 16 jugadores |
| lectura | Consulta identica al adaptador de la API {_id: 'ARG'} | notebook | pymongo | FALLA | 1 | sin resultados: en los datos del Hito 4 el _id es un ObjectId y el codigo FIFA esta en el campo 'codigo'. El cliente nativo funciona, pero la API respondera 404 para un … |
| lectura | [negativo] Documento inexistente {codigo: 'ZZZ'} | notebook | pymongo | OK | 1 | None (ausencia valida: la base respondio) |
| lectura | mongosh: ping + database + lectura de un equipo (dentro del contenedor) | contenedor | mongosh | OK | 480 | {"ping":1,"version":"7.0.45","db":"fixture2030","equipos":64,"equipo":{"codigo":"ARG","nombre":"Argentina"}} |
| api | GET /equipos/ARG | notebook | HTTP (urllib) -> API Hito 10 | FALLA | 13 | HTTP 404 recurso_inexistente / NOT_FOUND: No existe el equipo 'ARG'. |
| api | GET /equipos/ZZZ | notebook | HTTP (urllib) -> API Hito 10 | OK | 3 | HTTP 404 recurso_inexistente / NOT_FOUND: No existe el equipo 'ZZZ'. |
| api | GET /equipos/ARG/jugadores?limit=5 | notebook | HTTP (urllib) -> API Hito 10 | FALLA | 13 | HTTP 500 error_interno / INTERNAL_ERROR: Ocurrio un error interno al procesar la solicitud. |
| api | GET /equipos/ARG/jugadores?limit=0 | notebook | HTTP (urllib) -> API Hito 10 | OK | 24 | HTTP 400 error_validacion / VALIDATION_ERROR: Parametros o cuerpo invalidos. |

## neo4j

| Capa | Prueba | Origen | Cliente | Resultado | ms | Detalle |
| :--- | :--- | :--- | :--- | :---: | ---: | :--- |
| configuracion | Variables de conexion completas y validas | notebook | lectura de configuracion | OK | - | NEO4J_URI=bolt://localhost:7687 [configuracion.env]; NEO4J_USER=neo4j [configuracion.env]; NEO4J_PASSWORD=definido (11 caracteres, oculto) [configuracion.env]; NEO4J_DAT… |
| configuracion | Driver de la API importable en este Python | notebook | neo4j | OK | - | neo4j 5.27.0 |
| configuracion | Estado del contenedor (informativo) | notebook | docker inspect | INFO | - | fixture2030-neo4j: running |
| resolucion | Resolver host (driver de la API) | notebook | socket.getaddrinfo | OK | - | localhost -> 127.0.0.1, ::1 |
| resolucion | Resolver host (Neo4j Browser / HTTP) | notebook | socket.getaddrinfo | OK | - | localhost -> 127.0.0.1, ::1 |
| tcp | Conexion TCP (driver de la API) | notebook | socket.create_connection | OK | 1 | exito: conexion establecida ::1 -> ::1:7687 |
| tcp | TCP por familia de direcciones (driver de la API) | notebook | socket.create_connection | INFO | - | 127.0.0.1 -> exito (15 ms); ::1 -> exito (0 ms) |
| tcp | Conexion TCP (Neo4j Browser / HTTP) | notebook | socket.create_connection | OK | 1 | exito: conexion establecida ::1 -> ::1:7474 |
| tcp | TCP por familia de direcciones (Neo4j Browser / HTTP) | notebook | socket.create_connection | INFO | - | 127.0.0.1 -> exito (0 ms); ::1 -> exito (13 ms) |
| tcp | [negativo] Error de conexion (puerto Bolt sin listener) | notebook | neo4j (driver Bolt) | OK | 4105 | ServiceUnavailable: Couldn't connect to localhost:7688 (resolved to ()): |
| protocolo | Portal HTTP (Neo4j Browser / discovery) | notebook | HTTP GET | OK | 6 | HTTP 200: neo4j_version=2026.10.0 edition=community bolt_direct=bolt://localhost:7687 |
| protocolo | Handshake Bolt (bytes del protocolo, sin driver) | notebook | socket (magic 0x6060B017) | OK | 27 | servidor acepto Bolt 5.8 |
| autenticacion | Identidad 'neo4j' autentica por Bolt | notebook | neo4j (driver Bolt) | OK | 24 | autenticacion aceptada |
| autenticacion | [negativo] Password invalida | notebook | neo4j (driver Bolt) | OK | 21 | rechazada: Neo.ClientError.Security.Unauthorized |
| autorizacion | Permisos del usuario autenticado | notebook | neo4j (driver Bolt) | INFO | - | Neo4j Community no tiene control de acceso por roles: un usuario autenticado puede leer todas las databases. La autorizacion no se puede separar de la autenticacion en e… |
| contexto | Database 'neo4j' existe y esta online | notebook | neo4j (driver Bolt) | OK | 7 | currentStatus=online |
| contexto | [negativo] Database inexistente | notebook | neo4j (driver Bolt) | OK | 3 | error esperado: Neo.ClientError.Database.DatabaseNotFound |
| lectura | Lectura Cypher parametrizada y acotada (partido F2030-001) | notebook | neo4j (driver Bolt) | OK | 4 | {"partido": "F2030-001", "fecha": "2030-06-14", "eventos": 2} |
| lectura | [negativo] Partido inexistente (F2030-999) | notebook | neo4j (driver Bolt) | OK | 3 | 0 filas y sin error: la base respondio; la API lo traduce a 404 |
| lectura | [negativo] Partido existente sin eventos (resultado vacio valido) | notebook | neo4j (driver Bolt) | OK | 3 | F2030-006 existe y tiene 0 eventos: la API debe responder 200 con lista vacia, no 404 |
| lectura | cypher-shell: lectura parametrizada (dentro del contenedor) | contenedor | cypher-shell | OK | 1849 | partido, eventos / "F2030-001", 2 |
| api | GET /partidos/F2030-001/eventos?limit=5 | notebook | HTTP (urllib) -> API Hito 10 | OK | 10 | HTTP 200 exito / 2 eventos |
| api | GET /partidos/F2030-006/eventos?limit=5 | notebook | HTTP (urllib) -> API Hito 10 | OK | 10 | HTTP 200 vacio_valido / 0 eventos |
| api | GET /partidos/F2030-999/eventos | notebook | HTTP (urllib) -> API Hito 10 | OK | 7 | HTTP 404 recurso_inexistente / NOT_FOUND: No existe el partido 'F2030-999'. |

## cassandra

| Capa | Prueba | Origen | Cliente | Resultado | ms | Detalle |
| :--- | :--- | :--- | :--- | :---: | ---: | :--- |
| configuracion | Variables de conexion completas y validas | notebook | lectura de configuracion | OK | - | CASSANDRA_HOST=localhost [configuracion.env]; CASSANDRA_PORT=9042 [configuracion.env]; CASSANDRA_KEYSPACE=fixture2030_comentarios [configuracion.env]; CASSANDRA_CONTAINE… |
| configuracion | Driver de la API importable en este Python | notebook | cassandra-driver | OK | - | cassandra-driver 3.29.2 |
| configuracion | Estado del contenedor (informativo) | notebook | docker inspect | INFO | - | fixture2030-cassandra: running |
| resolucion | Resolver host (driver de la API) | notebook | socket.getaddrinfo | OK | - | localhost -> 127.0.0.1, ::1 |
| tcp | Conexion TCP (driver de la API) | notebook | socket.create_connection | OK | 1 | exito: conexion establecida ::1 -> ::1:9042 |
| tcp | TCP por familia de direcciones (driver de la API) | notebook | socket.create_connection | INFO | - | 127.0.0.1 -> exito (0 ms); ::1 -> exito (0 ms) |
| tcp | [negativo] Timeout de conexion (direccion sin respuesta) | notebook | cassandra-driver | OK | 3016 | NoHostAvailable: ('Unable to connect to any servers', {'10.255.255.1:9042': OSError(None, "Tried connecting to [('10.255.255.1', 9042)]. Last error: timed out")}) |
| protocolo | Handshake CQL: frame OPTIONS -> SUPPORTED (sin driver) | notebook | socket (frame CQL v4) | OK | 3 | SUPPORTED: CQL_VERSION=['3.4.7'] PROTOCOL_VERSIONS=['3/v3', '4/v4', '5/v5', '6/v6-beta'] |
| autenticacion | Frame STARTUP: el servidor exige autenticacion? | notebook | socket (frame CQL v4) | OK | 2 | READY: el servidor NO exige autenticacion (AllowAllAuthenticator del laboratorio); no hay identidad que validar |
| autenticacion | Sesion abierta con el driver de la API | notebook | cassandra-driver | OK | 1601 | Cassandra 5.0.9, cluster 'fixture2030-lab' |
| autorizacion | Permisos sobre el keyspace | notebook | cassandra-driver | INFO | - | sin autenticacion no hay autorizacion por rol (AllowAllAuthorizer): cualquier cliente que llegue al puerto puede leer y escribir |
| contexto | Keyspace 'fixture2030_comentarios' existe | notebook | cassandra-driver | OK | 15 | replicacion={'class': 'org.apache.cassandra.locator.SimpleStrategy', 'replication_factor': '1'} |
| contexto | Tabla comentarios_por_partido y patron de particion | notebook | cassandra-driver | OK | 15 | PRIMARY KEY ((partido_id, ventana), creado_en, comentario_id) |
| contexto | [negativo] Sesion sin keyspace seleccionado (tabla sin calificar) | notebook | cassandra-driver | OK | 16 | InvalidRequest: Error from server: code=2200 [Invalid query] message="No keyspace has been specified. USE a keyspace, or explicitly specify keyspace.tablename" |
| contexto | [negativo] Keyspace inexistente | notebook | cassandra-driver | OK | 15 | InvalidRequest: Error from server: code=2200 [Invalid query] message="Keyspace 'fixture2030_comentarios_inexistente_h11' does not exist" |
| contexto | [negativo] Tabla inexistente | notebook | cassandra-driver | OK | 15 | InvalidRequest: Error from server: code=2200 [Invalid query] message="table tabla_inexistente_h11 does not exist" |
| lectura | Lectura limitada de UNA particion (F2030-063, 2030-06-22 20:00Z) LIMIT 5 | notebook | cassandra-driver | OK | 16 | 2 filas |
| lectura | [negativo] Particion sin datos (ventana de 2029) | notebook | cassandra-driver | OK | 15 | 0 filas sin error: respuesta vacia valida |
| lectura | [negativo] Consulta invalida (filtro fuera de la clave, sin ALLOW FILTERING) | notebook | cassandra-driver | OK | 15 | InvalidRequest: Error from server: code=2200 [Invalid query] message="Cannot execute this query as it might involve data filtering and thus may have unpredictable perfor… |
| lectura | cqlsh: lectura limitada de una particion (dentro del contenedor) | contenedor | cqlsh | OK | 516 | (2 rows) |
| api | GET /partidos/F2030-063/comentarios?instante=2030-06-22T20%3A03%3A00Z&limit=5 | notebook | HTTP (urllib) -> API Hito 10 | OK | 7 | HTTP 200 exito / 2 comentarios |
| api | GET /partidos/F2030-063/comentarios?instante=2029-06-22T20%3A03%3A00Z&limit=5 | notebook | HTTP (urllib) -> API Hito 10 | OK | 32 | HTTP 200 vacio_valido / 0 comentarios |
| api | GET /partidos/F2030-063/comentarios?instante=no-es-fecha | notebook | HTTP (urllib) -> API Hito 10 | OK | 2 | HTTP 400 error_validacion / VALIDATION_ERROR: El parametro 'instante' no es una fecha-hora ISO-8601 valida. |

## redis

| Capa | Prueba | Origen | Cliente | Resultado | ms | Detalle |
| :--- | :--- | :--- | :--- | :---: | ---: | :--- |
| configuracion | Variables de conexion completas y validas | notebook | lectura de configuracion | OK | - | REDIS_URL=redis://localhost:6379/0 [sin credencial] [configuracion.env] |
| configuracion | Driver de la API importable en este Python | notebook | redis | OK | - | redis 5.2.1 |
| configuracion | Estado del contenedor (informativo) | notebook | docker inspect | INFO | - | fixture2030-redis: running |
| resolucion | Resolver host (driver de la API) | notebook | socket.getaddrinfo | OK | - | localhost -> 127.0.0.1, ::1 |
| tcp | Conexion TCP (driver de la API) | notebook | socket.create_connection | OK | 1 | exito: conexion establecida ::1 -> ::1:6379 |
| tcp | TCP por familia de direcciones (driver de la API) | notebook | socket.create_connection | INFO | - | 127.0.0.1 -> exito (0 ms); ::1 -> exito (0 ms) |
| protocolo | Handshake RESP: PING crudo (sin driver) | notebook | socket (RESP) | OK | 3 | +PONG (respuesta RESP basica, sin autenticar) |
| autenticacion | PING con el cliente de la API (aplica AUTH si la URL tiene password) | notebook | redis-py | OK | 3 | PONG |
| autenticacion | [negativo] AUTH con password invalida | notebook | redis-py | OK | 0 | el servidor NO tiene password configurada (requirepass vacio): no hay identidad que validar |
| autorizacion | Permisos del usuario 'default' | notebook | redis-py | INFO | - | sin ACL configuradas: el usuario default tiene acceso a todas las claves y comandos |
| contexto | Base logica 0: DBSIZE | notebook | redis-py | OK | 3 | 324 claves |
| lectura | Clave de demostracion 'sesion:S0001': tipo, TTL y campos | notebook | redis-py | OK | 1 | existe, tipo=hash, TTL=937 s, usuario_id=U0001, estado=activa |
| lectura | Operacion identica al adaptador de la API: GET sesion:S0001 | notebook | redis-py | FALLA | 0 | ResponseError: WRONGTYPE Operation against a key holding the wrong kind of value: el Hito 7 guarda la sesion como HASH y la API usa GET (string). La API traduce este err… |
| lectura | [negativo] Clave ausente 'sesion:no-existe-h11' | notebook | redis-py | OK | 1 | EXISTS=0, TTL=-2: Redis respondio; ausencia valida (404 en la API, no 503) |
| lectura | Clave expirada vs ausente: contadores del servidor | notebook | redis-py | INFO | 1 | expired_keys=20 evicted_keys=0 / una clave expirada se ve igual que una ausente (TTL=-2); solo los contadores del servidor o la aplicacion pueden distinguirlas |
| lectura | redis-cli: PING, TYPE y TTL de sesion:S0001 (dentro del contenedor) | contenedor | redis-cli | OK | 186 | PONG / hash / 937 / redis_version:8.10.2 |
| api | GET /sesiones/S0001 | notebook | HTTP (urllib) -> API Hito 10 | FALLA | 2 | HTTP 503 dependencia_no_disponible / DEPENDENCY_UNAVAILABLE: La fuente 'redis' no esta disponible en este momento. |
| api | GET /sesiones/no-existe-h11 | notebook | HTTP (urllib) -> API Hito 10 | OK | 19 | HTTP 404 recurso_inexistente / NOT_FOUND: No existe una sesion vigente con ese identificador. |

## influxdb

| Capa | Prueba | Origen | Cliente | Resultado | ms | Detalle |
| :--- | :--- | :--- | :--- | :---: | ---: | :--- |
| configuracion | Variables de conexion completas y validas | notebook | lectura de configuracion | OK | - | INFLUX_URL=http://localhost:8181 [configuracion.env]; INFLUX_DATABASE=fixture2030_vivo [configuracion.env]; INFLUXDB3_TOKEN=definido (92 caracteres, oculto) [archivo INF… |
| configuracion | Driver de la API importable en este Python | notebook | biblioteca estandar | OK | - | biblioteca estandar |
| configuracion | Estado del contenedor (informativo) | notebook | docker inspect | INFO | - | fixture2030-influxdb: running |
| resolucion | Resolver host (driver de la API) | notebook | socket.getaddrinfo | OK | - | localhost -> 127.0.0.1, ::1 |
| tcp | Conexion TCP (driver de la API) | notebook | socket.create_connection | OK | 2039 | exito: conexion establecida 127.0.0.1 -> 127.0.0.1:8181 |
| tcp | TCP por familia de direcciones (driver de la API) | notebook | socket.create_connection | INFO | - | 127.0.0.1 -> exito (0 ms); ::1 -> refused (2040 ms) / la conexion por nombre tardo 2039 ms: el primer intento va a una direccion sin listener |
| protocolo | GET /health SIN token | notebook | HTTP API v3 | OK | 2065 | HTTP 401: el servicio responde HTTP; exige autorizacion incluso para /health (InfluxDB 3 Core por defecto) |
| autenticacion | GET /health CON el token configurado | notebook | HTTP API v3 | OK | 2041 | HTTP 200 OK |
| autenticacion | [negativo] Token invalido | notebook | HTTP API v3 | OK | 2055 | HTTP 401 (rechazado) |
| autorizacion | El token puede listar las databases (permiso de administracion) | notebook | HTTP API v3 | OK | 2041 | HTTP 200: _internal, fixture2030_historico, fixture2030_resumen, fixture2030_vivo |
| contexto | Database 'fixture2030_vivo' configurada existe | notebook | HTTP API v3 | OK | - | presente en el catalogo |
| contexto | [negativo] Database inexistente | notebook | HTTP API v3 | OK | 2041 | HTTP 404: {"error":"query error: database not found: fixture2030_vivo_inexistente_h11"} |
| lectura | Consulta temporal acotada F2030-018 [2030-06-13T08:00:00Z, 2030-06-13T08:05:00Z): COUNT, AVG(posesion), MAX(p… | notebook | HTTP API v3 | OK | 2058 | [{"equipo_id": "ALG", "puntos": 300, "posesion_prom": 50.0, "pases_al_cierre": 20}, {"equipo_id": "TUN", "puntos": 300, "posesion_prom": 50.0, "pases_al_cierre": 38}] |
| lectura | [negativo] Ventana sin puntos [2030-06-13T09:00:00Z, 2030-06-13T09:15:00Z) | notebook | HTTP API v3 | OK | 2034 | HTTP 200 con [] : ausencia de puntos, no error |
| lectura | influxdb3 query: conteo en la ventana (dentro del contenedor) | contenedor | influxdb3 CLI | OK | 122 | puntos=600 / influxdb3 InfluxDB 3 Core, 3.12.1, revision 692ea4a9943fc343c5fdf830d7dff82eef1f7fca |
| api | GET /partidos/F2030-018/estadisticas?desde=2030-06-13T08%3A00%3A00Z&hasta=2030-06-13T08%3A05%3A00Z | notebook | HTTP (urllib) -> API Hito 10 | FALLA | 2037 | HTTP 503 dependencia_no_disponible / DEPENDENCY_UNAVAILABLE: La fuente 'influxdb' no esta disponible en este momento. |
| api | GET /partidos/F2030-018/estadisticas?desde=2030-06-13T09%3A00%3A00Z&hasta=2030-06-13T09%3A15%3A00Z | notebook | HTTP (urllib) -> API Hito 10 | FALLA | 2041 | HTTP 503 dependencia_no_disponible / DEPENDENCY_UNAVAILABLE: La fuente 'influxdb' no esta disponible en este momento. |
| api | GET /partidos/F2030-018/estadisticas?desde=2030-06-13T08%3A05%3A00Z&hasta=2030-06-13T08%3A00%3A00Z | notebook | HTTP (urllib) -> API Hito 10 | OK | 2 | HTTP 400 error_validacion / VALIDATION_ERROR: El parametro 'desde' debe ser anterior a 'hasta'. |

## iris

| Capa | Prueba | Origen | Cliente | Resultado | ms | Detalle |
| :--- | :--- | :--- | :--- | :---: | ---: | :--- |
| configuracion | Variables de conexion completas y validas | notebook | lectura de configuracion | OK | - | IRIS_HOST=localhost [configuracion.env]; IRIS_PORT=1972 [configuracion.env]; IRIS_NAMESPACE=USER [configuracion.env]; IRIS_USER=_SYSTEM [configuracion.env]; IRIS_PASSWOR… |
| configuracion | Driver de la API importable en este Python | notebook | intersystems-irispython | OK | - | intersystems-irispython |
| configuracion | Estado del contenedor (informativo) | notebook | docker inspect | INFO | - | fixture2030-iris: running |
| resolucion | Resolver host (driver de la API (Superserver)) | notebook | socket.getaddrinfo | OK | - | localhost -> 127.0.0.1, ::1 |
| resolucion | Resolver host (Management Portal) | notebook | socket.getaddrinfo | OK | - | localhost -> 127.0.0.1, ::1 |
| tcp | Conexion TCP (driver de la API (Superserver)) | notebook | socket.create_connection | OK | 2041 | exito: conexion establecida 127.0.0.1 -> 127.0.0.1:1972 |
| tcp | TCP por familia de direcciones (driver de la API (Superserver)) | notebook | socket.create_connection | INFO | - | 127.0.0.1 -> exito (0 ms); ::1 -> refused (2043 ms) / la conexion por nombre tardo 2041 ms: el primer intento va a una direccion sin listener |
| tcp | Conexion TCP (Management Portal) | notebook | socket.create_connection | OK | 2042 | exito: conexion establecida 127.0.0.1 -> 127.0.0.1:52773 |
| tcp | TCP por familia de direcciones (Management Portal) | notebook | socket.create_connection | INFO | - | 127.0.0.1 -> exito (15 ms); ::1 -> refused (2043 ms) / la conexion por nombre tardo 2042 ms: el primer intento va a una direccion sin listener |
| protocolo | Management Portal HTTP | notebook | HTTP GET | OK | 2055 | HTTP 200 (pagina de login) |
| autenticacion | Conexion al Superserver como '_SYSTEM' en 'USER' | notebook | intersystems-irispython | FALLA | 2020 | Superserver responde y la identidad existe, pero la password esta EXPIRADA (IRIS Community exige cambiarla en el primer ingreso). La API no puede abrir sesion: RuntimeEr… |
| contexto | [negativo] Terminal con namespace incorrecto | contenedor | iris session | OK | 181 | Node: ac4fc74fb0a5, Instance: IRIS Access Denied |
| lectura | Terminal (iris session): existe F2030-001 por indice CodigoIdx | contenedor | iris session | OK | 181 | NS=USER EXISTE=1 / VERSION=IRIS for UNIX (Ubuntu Server LTS for x86-64 Containers) 2026.2 (Build 221U) Fri Jun 26 2026 09:58:52 EDT |
| api | GET /partidos/F2030-001/detalle | notebook | HTTP (urllib) -> API Hito 10 | FALLA | 2021 | HTTP 503 dependencia_no_disponible / DEPENDENCY_UNAVAILABLE: La fuente 'iris' no esta disponible en este momento. |
| api | GET /partidos/F2030-999/detalle | notebook | HTTP (urllib) -> API Hito 10 | FALLA | 2021 | HTTP 503 dependencia_no_disponible / DEPENDENCY_UNAVAILABLE: La fuente 'iris' no esta disponible en este momento. |

## api

| Capa | Prueba | Resultado | ms | Detalle |
| :--- | :--- | :---: | ---: | :--- |
| api | GET /salud contra un puerto sin API | OK | 2050 | sin respuesta HTTP (connection refused): API no alcanzable |
| api | GET /salud (chequeo de las 6 fuentes) | INFO | 6185 | HTTP 200 en 6185 ms / mongodb=si, neo4j=si, cassandra=si, redis=si, influxdb=no, iris=no |

## demostracion

| Capa | Prueba | Resultado | ms | Detalle |
| :--- | :--- | :---: | ---: | :--- |
| tcp | Tipo de falla 'exito': Puerto publicado por el contenedor de Redis | OK | 16 | exito: conexion establecida ::1 -> ::1:6379 |
| tcp | Tipo de falla 'refused': Puerto donde no escucha ningun proceso | OK | 4086 | refused: connection refused: el host respondio pero no hay listener |
| tcp | Tipo de falla 'timeout': Direccion no enrutable: nadie contesta | OK | 3008 | timeout: sin respuesta en 3.0 s |
| tcp | Tipo de falla 'no_resuelto': Nombre de servicio de Docker usado desde la notebook (solo existe dentro de la r… | OK | 2695 | no_resuelto: host no resuelto (getaddrinfo failed) |
| protocolo | Tipo de falla 'puerto incorrecto': handshake Bolt contra el puerto HTTP 7474 de Neo4j | OK | - | TCP exito, pero la respuesta al handshake Bolt fue b'HTTP/1.1 400 Bad Request': el listener habla HTTP, no Bolt |

## herramientas

| Capa | Prueba | Resultado | ms | Detalle |
| :--- | :--- | :---: | ---: | :--- |
| configuracion | Docker disponible para clientes nativos | INFO | - | Docker Engine 29.8.2 |

## topologia

| Capa | Prueba | Resultado | ms | Detalle |
| :--- | :--- | :---: | ---: | :--- |
| tcp | localhost dentro del contenedor = el propio contenedor de Redis | INFO | - | exito (EXITO) |
| tcp | Mongo NO corre en este contenedor: localhost:27017 no es la notebook | INFO | - | refused_o_timeout (FALLA_TCP) |
| tcp | Puerto publicado de Mongo visto desde un contenedor (Docker Desktop) | INFO | - | exito (EXITO) |
| tcp | Nombre de otro contenedor: esta en otra red de Compose | INFO | - | no_resuelto (NO_RESUELVE) |

## Herramientas o pruebas no ejecutadas (SKIP)

- ninguna
