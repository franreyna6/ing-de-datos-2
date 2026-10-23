# Capas de evaluación

**Grupo 8** · Fixture 2030 · Hito 11 (RNF2, RNF4, secciones 5.2 a 5.4)

La evaluación avanza **de menor a mayor costo**. Una capa solo se intenta si la anterior dejó
algo que probar: si el host no resuelve, no se intenta TCP (queda SKIP con el motivo), y si falta
la variable obligatoria, el producto queda `no_configurado` sin abrir ninguna conexión.

| # | Capa | Pregunta que responde | Qué NO permite concluir todavía | Script |
| :---: | :--- | :--- | :--- | :--- |
| 1 | Configuración | ¿Existen las variables que usa la API, son válidas y de dónde salen? | Que el valor sea correcto (una password definida puede ser incorrecta) | `prueba_configuracion.py` |
| 2 | Resolución | ¿El nombre configurado se convierte en una dirección **desde el origen de la API**? | Que haya un proceso escuchando | `prueba_tcp.py` |
| 3 | TCP | ¿Hay un listener aceptando conexiones en host:puerto? | Que sea el producto correcto, que hable su protocolo, que esté vivo detrás de un proxy | `prueba_tcp.py` |
| 4 | Protocolo | ¿El listener habla el protocolo del producto (handshake)? | Que la identidad sea válida | `prueba_clientes_nativos.py` |
| 5 | Autenticación | ¿La identidad configurada es aceptada? | Que tenga permiso sobre el contexto | ídem |
| 6 | Autorización | ¿La identidad puede operar sobre el recurso? | Que el contexto sea el que tiene los datos | ídem |
| 7 | Contexto | ¿Existe la database / keyspace / namespace / tabla configurada? | Que los datos de prueba existan o que la consulta de la API sea válida | ídem |
| 8 | Lectura mínima | ¿Se puede leer un dato del módulo con el cliente adecuado? ¿La **operación idéntica a la del adaptador** funciona? | Rendimiento ni disponibilidad sostenida | ídem |
| 9 | Endpoint de la API | ¿La cadena cliente HTTP → API → adaptador → producto responde según el contrato? | Capacidad o escalabilidad (eso es el Hito 12) | `prueba_api.py` |

## Origen de cada prueba (RNF3)

- **notebook:** el mismo proceso, el mismo Python (3.11 de `api/.venv`), los mismos drivers y la
  misma configuración que la API. Es lo que decide el estado de la dependencia.
- **contenedor:** el cliente nativo del producto (`mongosh`, `cypher-shell`, `cqlsh`, `redis-cli`,
  `influxdb3`, `iris session`) ejecutado con `docker exec`. Prueba que el producto funciona “desde
  adentro”, pero **no** prueba la ruta que usa la API. Por eso no cuenta para el estado.

## Casos negativos

Cada producto tiene pruebas que **deben fallar** de una forma específica (credencial inválida,
contexto inexistente, recurso inexistente, consulta inválida, puerto sin listener). Su resultado
es `OK` cuando el producto devuelve el **error esperado y distinguible**. No cuentan para el estado
de salud: sirven para demostrar que el diagnóstico separa causas que la API, hoy, junta en un 503.

## Tipos de resultado TCP (tabla 5.3) — observados

`prueba_tcp.py --demostrar-fallas` provoca cada tipo **sin detener ni modificar ningún producto**.
Corrida final (`evidencia/corridas/20261023_032545_final/resultados_tcp.txt`):

| Resultado | Caso provocado | Tiempo | Interpretación |
| :--- | :--- | ---: | :--- |
| Conexión exitosa | `localhost:6379` (Redis publicado) | 15 ms | Existe un listener accesible en el host y puerto probados |
| Connection refused | `localhost:27018` (sin proceso) | 4.094 ms | El host respondió, pero no hay listener. En Windows el rechazo llega tras reintentar en `::1` y `127.0.0.1` (~2 s cada uno) |
| Timeout | `10.255.255.1:27017` (no enrutable) | 3.013 ms | Nadie contestó dentro del límite (3 s): red, firewall, ruta o saturación |
| Host no resuelto | `mongodb:27017` desde la notebook | 2.687 ms | El nombre del servicio de Docker solo existe dentro de su red de Compose |
| Puerto incorrecto | handshake Bolt contra `localhost:7474` | — | El TCP **conecta**, pero el listener responde `HTTP/1.1 400 Bad Request`: es HTTP, no Bolt |

Y un sexto caso, observado en la falla controlada: con **Redis detenido** el TCP a `6379` **tuvo
éxito** (proxy de puertos de Docker Desktop) y el `PING` crudo no recibió respuesta. Una
conexión TCP exitosa nunca se presenta como prueba de autenticación, contexto o consulta válida.

## Pruebas por producto

### MongoDB (RF9)

| Capa | Prueba | Responde | No permite concluir |
| :--- | :--- | :--- | :--- |
| TCP | `localhost:27017` | hay listener | que sea Mongo |
| Protocolo | comando `hello` **sin** credencial (pymongo) | el listener habla Wire Protocol (`maxWireVersion=21`) | que la credencial sirva |
| Autenticación | `connectionStatus` con `MONGODB_URI` | la identidad es aceptada (`admin@admin`) | permisos sobre `fixture2030` |
| Autenticación (neg.) | misma URI con password inválida | se distingue credencial inválida (code 18) de servidor caído | — |
| Autorización | `list_collection_names()` en `fixture2030` | la identidad opera en la database | — |
| Contexto | `fixture2030` en `listDatabases` con `equipos` y `jugadores` | es la database del Hito 4 | — |
| Contexto (neg.) | database inexistente | **Mongo no da error**: la lectura vuelve vacía. Solo el catálogo revela el error de contexto | — |
| Lectura | `find_one({codigo: 'ARG'})`, conteo de jugadores con `limit` | el cliente lee el módulo | rendimiento |
| Lectura (API) | `find_one({_id: 'ARG'})`, **la consulta del adaptador** | **falla**: cliente nativo OK y API fallando (H1) | — |
| Contenedor | `mongosh`: ping + `findOne` | el producto funciona desde adentro | la ruta de la notebook |

### Neo4j (RF10)

| Capa | Prueba | Responde | No permite concluir |
| :--- | :--- | :--- | :--- |
| Protocolo (HTTP) | `GET http://localhost:7474/` (discovery) | el portal/Browser responde (versión 2026.10.0 community) | **nada sobre Bolt**, que es lo que usa la API |
| Protocolo (Bolt) | bytes del handshake (`0x6060B017` + versiones) sin driver | el puerto 7687 habla Bolt y acepta 5.8 | credencial |
| Autenticación | `verify_authentication()` | usuario y password aceptados | database |
| Autenticación (neg.) | password inválida | `Neo.ClientError.Security.Unauthorized` | — |
| Autorización | — (INFO) | Community no tiene RBAC: no se puede separar de la autenticación | — |
| Contexto | `SHOW DATABASE neo4j` | existe y está `online` | que tenga los datos |
| Contexto (neg.) | database inexistente | `Neo.ClientError.Database.DatabaseNotFound` | — |
| Lectura | `MATCH (p:Partido {codigo:$codigo})` parametrizado + `LIMIT` | el grafo del Hito 5 responde (F2030-001, 2 eventos) | — |
| Lectura (neg.) | partido inexistente / partido sin eventos / puerto 7688 | **0 filas** ≠ **lista vacía de un partido que existe** ≠ **ServiceUnavailable** | — |

### Cassandra (RF11)

| Capa | Prueba | Responde | No permite concluir |
| :--- | :--- | :--- | :--- |
| Protocolo | frame CQL `OPTIONS` → `SUPPORTED` (sin driver) | habla CQL 3.4.7, protocolos v3–v6 | keyspace |
| Autenticación | frame `STARTUP` → `READY` | el servidor **no exige** autenticación (laboratorio) | — |
| Autenticación | sesión con `cassandra-driver` | el driver de la API abre sesión (Cassandra 5.0.9) | — |
| Contexto | `system_schema.keyspaces` y `system_schema.columns` | existe el keyspace y la tabla con `PRIMARY KEY ((partido_id, ventana), creado_en, comentario_id)` | — |
| Contexto (neg.) | keyspace inexistente / tabla inexistente / sin keyspace | `InvalidRequest` específico en cada caso | — |
| Lectura | `SELECT … WHERE partido_id=? AND ventana=? LIMIT 5` (una partición) | lee la partición que pide la API (2 filas) | — |
| Lectura (neg.) | filtro fuera de la clave sin `ALLOW FILTERING` → `InvalidRequest` en 16 ms; dirección sin respuesta → `NoHostAvailable` en 3.002 ms | **consulta inválida ≠ timeout de conexión** | — |

### Redis (RF12)

| Capa | Prueba | Responde | No permite concluir |
| :--- | :--- | :--- | :--- |
| Protocolo | `PING` en RESP crudo | `+PONG`: respuesta básica del servidor | claves |
| Autenticación | `PING` con redis-py; `AUTH` inválido | el servidor no tiene password (`requirepass` vacío) | — |
| Contexto | `DBSIZE` de la base 0 | 324 claves | una base vacía no es una falla de conexión |
| Lectura | `TYPE`, `TTL`, `HMGET` de `sesion:S0001` | existe, es **hash**, TTL restante, `estado=activa` | — |
| Lectura (API) | `GET sesion:S0001`, **la operación del adaptador** | **WRONGTYPE** (H2) | — |
| Lectura (neg.) | clave ausente: `EXISTS=0`, `TTL=-2` | ausencia válida (404), no caída (503) | — |
| Lectura | `INFO stats` (`expired_keys`) | una clave **expirada** se ve igual que una **ausente**: solo los contadores la distinguen | — |
| Caída | `docker stop` (falla controlada) | `ConnectionError` ≠ clave ausente | — |

### InfluxDB (RF13)

| Capa | Prueba | Responde | No permite concluir |
| :--- | :--- | :--- | :--- |
| Protocolo | `GET /health` **sin** token | `401`: el servicio responde, pero exige autorización incluso para `/health` | — |
| Autenticación | `GET /health` con token / con token inválido | `200 OK` / `401` | permisos sobre la database |
| Autorización | `GET /api/v3/configure/database` | el token puede listar databases | — |
| Contexto | `fixture2030_vivo` en el catálogo; database inexistente | presente / `404 database not found` | — |
| Lectura | ventana `[08:00, 08:05)` de F2030-018 con `COUNT`, `AVG(posesion_pct)`, `MAX(pases_acum)` | rango y agregación correctos para cada medida (300 puntos por equipo) | — |
| Lectura (neg.) | ventana sin puntos `[09:00, 09:15)` | `200 []`: **ausencia de puntos ≠ error** | — |
| Lectura (API) | el mismo cuerpo JSON que arma el adaptador | **400 `missing field q`** (H6) | — |

### IRIS (RF14)

| Capa | Prueba | Responde | No permite concluir |
| :--- | :--- | :--- | :--- |
| Protocolo (HTTP) | Management Portal `/csp/sys/UtilHome.csp` | `200` (login): el portal responde | **nada sobre el Superserver** |
| Autenticación + contexto | `iris.connect(host, 1972, USER, _SYSTEM, ***)` | Superserver, identidad y namespace en un solo paso | — |
| Contexto | `INFORMATION_SCHEMA.TABLES` del esquema `Fixture` | 9 tablas: las clases del Hito 9 están compiladas | — |
| Autorización | `SELECT COUNT(*) FROM Fixture.Partido` | permiso de lectura (96 partidos) | — |
| Lectura | `Fixture.Partido` por `Codigo` | entidad del Hito 9 | — |
| Lectura (API) | el SQL exacto del adaptador | **SQLCODE -1** por el alias `local` (H7) | — |
| Contexto (neg.) | namespace `NOEXISTE_H11` (driver y Terminal) | `Access Denied` | — |
| Lectura (neg.) | `F2030-999` | sin filas y sin error: objeto inexistente ≠ Superserver inaccesible | — |
| Contenedor | `iris session` + `CodigoIdxExists` | el objeto existe | **la password del Superserver**: el Terminal entra con la identidad del SO del contenedor |
