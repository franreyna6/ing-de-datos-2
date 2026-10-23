# Diagnóstico de fallas y fallas controladas

**Grupo 8** · Fixture 2030 · Hito 11 (RF17, RF18, RF20, RF21, RNF10, RNF12, sección 5.7)

Cada falla tiene **hipótesis, prueba realizada, resultado y siguiente paso** (RNF10). Las que se
corrigieron con configuración o con el entorno tienen su **antes y después** (RF20). Las que
requieren cambiar el código de la API **no se corrigieron**: el alcance acordado para este hito
fue no modificar la API del Hito 10. Quedan como siguiente paso, con el cambio propuesto.

## 1. Hallazgos

| ID | Producto | Capa | Síntoma en la API | Estado |
| :--- | :--- | :--- | :--- | :--- |
| C0 | InfluxDB | autenticación | (preparación) token local ausente | corregido sin borrar datos |
| H1 | MongoDB | lectura (modelo) | `GET /equipos/ARG` → 404; `/jugadores` → 500 | pendiente (código) |
| H2 | Redis | lectura (tipo de dato) | `GET /sesiones/S0001` → 503 | pendiente (código) |
| H3 | IRIS | autenticación | `/detalle` → 503 tras ~2 s | corregido (C1) |
| H4 | InfluxDB, IRIS | resolución/TCP | ~2 s extra en cada conexión nueva | corregido (C2) |
| H5 | InfluxDB | contexto (esquema) | `/estadisticas` → 503 | corregido (C3) |
| H6 | InfluxDB | protocolo de la API v3 | `/estadisticas` → 503 siempre; `/salud` influxdb = no | pendiente (código) |
| H7 | IRIS | lectura (SQL) | `/detalle` → 503; `/salud` iris = sí | pendiente (código) |
| H8 | API | observabilidad | 500 sin header `X-Request-ID` ni línea de acceso | pendiente (código) |

### C0 — Token de InfluxDB ausente

- **Hipótesis:** el repositorio se clonó de nuevo y `influxdb/.influxdb3-token` (excluido de Git)
  quedó en la copia anterior; el servidor conserva su token de administración.
- **Prueba:** `curl -i http://127.0.0.1:8181/health` → `401 Unauthorized`: el servicio responde,
  no está caído. `influxdb3 create token --admin` no sirve si ya existe uno.
- **Resultado / corrección:** recuperación oficial de InfluxDB 3 Core
  (`INFLUXDB3_ADMIN_TOKEN_RECOVERY_HTTP_BIND_ADDR`, escuchando solo dentro del contenedor), con un
  override temporal fuera del repo, `create token --admin --regenerate`, y vuelta al compose
  original. `show databases` muestra las bases previas intactas.
- **Siguiente paso:** documentado en el README (preparación). No usar `limpieza.py --datos` del
  Hito 8 para este caso: borra los datos.
- **Evidencia:** [`evidencia/diagnostico/C0_influx_token_recuperado.txt`](evidencia/diagnostico/C0_influx_token_recuperado.txt).

### H1 — MongoDB: la API busca por `_id`, el Hito 4 guarda el código en `codigo`

- **Hipótesis:** si el cliente nativo encuentra el equipo y la API responde 404, la diferencia
  está en la operación, no en la conexión.
- **Prueba:** desde la notebook, con el mismo driver y la misma URI: `find_one({codigo:'ARG'})`
  → encontrado; `find_one({_id:'ARG'})` (la del adaptador) → `None`.
  En la API: `GET /equipos/ARG` → `404 NOT_FOUND`; `GET /equipos/ARG/jugadores?limit=5` → `500`
  (log: `ResponseValidationError`, porque la proyección `"codigo": "$_id"` devuelve un ObjectId).
- **Resultado:** cliente nativo funcionando y API fallando, el caso que pide la sección 5.4.
  Las capturas del Hito 10 mostraban 200 porque se probó con documentos cargados a mano con
  `_id = 'ARG'` y campos (`grupo`, `ciudadSede`) que el Hito 4 no tiene.
- **Siguiente paso (código, no aplicado):** en `mongo_adapter.py`, filtrar por `{"codigo": codigo}`
  y proyectar `codigo` (no `$_id`). Alternativa de datos: recargar el Hito 4 con `_id = codigo`.
- **Evidencia:** `corridas/20261023_032545_final/resultados_clientes.txt` y `resultados_api.txt`
  (request `h11-final-01-8fa9`).

### H2 — Redis: sesión como hash, lectura con `GET`

- **Hipótesis:** un 503 con PING OK indica que el error no es de disponibilidad.
- **Prueba:** `TYPE sesion:S0001` → `hash` (TTL de 1.800 s del Hito 7); `GET sesion:S0001` →
  `WRONGTYPE Operation against a key holding the wrong kind of value`.
  Log de la API: `dependencia fuente=redis causa=WRONGTYPE …` → `GET /sesiones/S0001 -> 503`.
- **Resultado:** la API convierte un **error de modelo** en **“Redis no disponible”**. Es la
  confusión que la sección 7 pide evitar (“una clave ausente no equivale a Redis caído”), en su
  variante “un tipo incorrecto no equivale a Redis caído”.
- **Siguiente paso (código):** leer con `HGETALL` (o `HMGET usuario_id estado`) y traducir
  `ResponseError` a un 500 de contrato, no a 503.
- **Evidencia:** request `h11-final-11-41b3`.

### H3 — IRIS: password expirada en la imagen Community

- **Hipótesis:** el Superserver responde (TCP OK) y el Portal también; el rechazo está en la identidad.
- **Prueba:** `iris.connect(…, '_SYSTEM', <password por defecto>)` → `Password change required`.
  Con `iris session` dentro del contenedor el objeto existe (`CodigoIdxExists = 1`), porque el
  Terminal entra con la identidad del sistema operativo y **no prueba la password del Superserver**.
- **Resultado:** identidad válida pero no utilizable: capa de **autenticación**, no de red.
  La API respondía 503 tras ~2 s.
- **Corrección (C1, entorno):** password local nueva para `_SYSTEM` con
  `Security.Users.Modify` (`ChangePassword=0`), guardada solo en `config/configuracion.env`.
  Después: autenticación OK en 22 ms, 9 tablas en `Fixture`, 96 partidos visibles.
- **Evidencia:** `corridas/20261023_031659_inicial/` (antes) y
  [`diagnostico/C1_iris_password_despues.txt`](evidencia/diagnostico/C1_iris_password_despues.txt).

### H4 — `localhost` resuelve primero a IPv6 y los puertos están publicados solo en IPv4

- **Hipótesis:** las pruebas contra InfluxDB e IRIS tardan siempre ~2 s, aun cuando son triviales.
- **Prueba:** TCP por familia: `127.0.0.1` → éxito en 0–15 ms; `::1` → *refused* en ~2.040 ms.
  Sus composes publican en `127.0.0.1:…` (los demás en `0.0.0.0` y `[::]`).
- **Resultado:** cada conexión nueva paga ~2 s antes de caer a IPv4. El adaptador de InfluxDB
  abre una conexión por request y el timeout es de 3 s: con un poco de carga, el margen se agota.
- **Corrección (C2, configuración):** `INFLUX_URL=http://127.0.0.1:8181`, `IRIS_HOST=127.0.0.1`,
  `IRIS_PORTAL_URL=http://127.0.0.1:52773`. TCP: 2.043 → 1 ms (InfluxDB), 2.058 → 15 ms (IRIS).
  `/salud`: 6.185 ms → 2.188 ms (el resto es la conexión inicial del driver de Cassandra, ~1,6 s).
- **Siguiente paso:** aplicar el mismo cambio en `api/.env.example` (no se tocó la API).
- **Evidencia:** [`diagnostico/C2_ipv6_antes.txt`](evidencia/diagnostico/C2_ipv6_antes.txt) y
  [`C2_ipv6_despues.txt`](evidencia/diagnostico/C2_ipv6_despues.txt).

### H5 — InfluxDB de la notebook con un esquema anterior del Hito 8

- **Hipótesis:** la consulta falla con `500` aun con token y database correctos, así que el
  problema está dentro del contexto.
- **Prueba:** `information_schema.columns` de `estadisticas_equipo` → `pases`, `tiros`,
  `recuperaciones`, `goles`, `minuto`. La API y el Hito 8 final usan `pases_acum`, `tiros_acum`,
  `recuperaciones_acum`. Las bases se llamaban `fixture2030_historico` y `fixture2030_resumen`,
  de una versión previa del módulo.
- **Resultado:** el contexto **existe** pero tiene **otro modelo**. Una prueba que solo verificara
  “database presente” lo habría dado por bueno.
- **Corrección (C3, entorno):** `generacion_puntos.py --perfil muestra` + `carga_lotes.py --perfil
  muestra` del Hito 8 actual (22.080 líneas OK, 0 rechazadas). No se borró nada: los puntos viejos
  siguen en la tabla y las columnas nuevas se agregaron. Después: la consulta nativa devuelve
  300 puntos por equipo con `MAX(pases_acum)`.
- **Evidencia:** [`diagnostico/H5_influx_esquema_antes.txt`](evidencia/diagnostico/H5_influx_esquema_antes.txt),
  [`diagnostico/C3_influx_recarga_esquema.txt`](evidencia/diagnostico/C3_influx_recarga_esquema.txt).

### H6 — InfluxDB: el adaptador envía `query`, la API v3 exige `q`

- **Hipótesis:** el log de la API registra `influx status=400`, no 401 ni 404; el servicio, el
  token y la database ya se probaron OK.
- **Prueba:** el mismo cuerpo JSON del adaptador, enviado a mano →
  `400 serde json error: missing field 'q'`. Con `q` → `200 [{"n":600}]`.
- **Resultado:** **todas** las consultas de la API a InfluxDB fallan, incluido el `verificar()` de
  `/salud`, que siempre informa `influxdb = no`. La ventana sin puntos, que debería ser
  `200 []`, también da 503.
- **Siguiente paso (código):** en `influx_adapter.py`, `"q": sql` en lugar de `"query": sql`, y
  traducir un `4xx` de InfluxDB a un error de contrato, no a 503.
- **Evidencia:** requests `h11-final-13-8088` y `h11-final-14-ebcf`; prueba nativa
  “Petición idéntica al adaptador”.

### H7 — IRIS: alias `local` reservado en IRIS SQL

- **Hipótesis:** tras C1, `/salud` informa `iris = sí`, pero `/detalle` sigue en 503. El
  `verificar()` ejecuta `SELECT 1` y el caso de uso ejecuta otra consulta.
- **Prueba:** el SQL exacto del adaptador → `SQLCODE -1: USING expected, LOCAL found`. El mismo
  SQL con el alias renombrado a `loc` → OK.
- **Resultado:** es el ejemplo de la secuencia por capas: al corregir la autenticación apareció
  la falla de la capa siguiente (operación). `/salud` en verde **no** garantiza el caso de uso.
- **Siguiente paso (código):** renombrar el alias en `iris_adapter.py` y traducir los errores SQL
  a 500 de contrato, no a 503.
- **Evidencia:** requests `h11-final-16-8d2d`, `h11-final-17-189f`; prueba nativa “SQL idéntico
  al adaptador”.

### H8 — Correlación incompleta en errores 500

- **Prueba:** `GET /equipos/ARG/jugadores?limit=1` con `X-Request-ID: h11-verif-500` → `500`. El
  cuerpo trae `request_id`, el log tiene `[req=h11-verif-500] error inesperado …`, pero **falta el
  header `X-Request-ID`** y **falta la línea de acceso** `GET … -> 500 (x ms)`: la excepción
  atraviesa el middleware antes de que registre status y duración.
- **Siguiente paso (código):** capturar la excepción dentro del middleware (o usar un handler de
  `ResponseValidationError`) para registrar siempre método, ruta, status y duración (RNF11).
- **Evidencia:** [`diagnostico/H8_request_id_en_500.txt`](evidencia/diagnostico/H8_request_id_en_500.txt).

## 2. Falla controlada principal: Redis detenido (RF21, sección 5.7)

Ejecutada con `scripts/falla_controlada.py --escenario redis_detenido`
([`evidencia/falla_controlada/resultados_falla_controlada.txt`](evidencia/falla_controlada/resultados_falla_controlada.txt)).

| Elemento (5.7) | Observado |
| :--- | :--- |
| **Condición inicial** | `fixture2030-redis` running · `DBSIZE=324` · `sesion:S0001` tipo hash, TTL 411 s · montaje `~/docker/data/redis → /data`. API: `GET /sesiones/no-existe-h11` → `404` en 64 ms (la base respondió) |
| **Cambio aplicado** | `docker stop fixture2030-redis` (0,5 s). Sin `down`, sin `-v`, sin tocar la carpeta de datos |
| **Prueba ejecutada** | TCP + `PING` crudo a `localhost`, `127.0.0.1` y `::1` · `PING` con redis-py · tres rutas de la API · `/salud` |
| **TCP** | **éxito** en las tres direcciones (proxy de puertos de Docker Desktop), pero el `PING` no tuvo respuesta: TCP exitoso ≠ disponible |
| **Respuesta de la API** | `/sesiones/no-existe-h11` → `503 DEPENDENCY_UNAVAILABLE` en 27 ms · `/sesiones/S0001` → `503` en 5 ms · **`/partidos/F2030-001/eventos` (Neo4j) → `200`** en 163 ms: la falla queda aislada en su ruta |
| **Mensaje de log** | `WARNING [req=h11-falla-redis-404] dependencia fuente=redis causa=Error while reading from localhost:6379 : (10053, …)` y `WARNING [req=h11-falla-redis-s01] dependencia fuente=redis causa=Connection closed by server.` → `GET /sesiones/S0001 -> 503 (3.2 ms)` ([`api_redis_detenido.log`](evidencia/falla_controlada/api_redis_detenido.log)) |
| **Tiempo de espera** | 503 en 5–27 ms: falla rápida, sin colgarse ni reintentar. `/salud` tardó 6.013 ms y respondió **200** con `redis=false` |
| **Recuperación** | `docker start fixture2030-redis` → `PONG` a los 0,5 s (1 intento, límite 60 s) |
| **Resultado después** | `/sesiones/no-existe-h11` → `404` en 15 ms: la API se reconectó sola, sin reiniciarla |
| **Datos conservados** | `DBSIZE` 324 → 324 · `sesion:S0001` sigue siendo hash, con TTL 404 s (AOF + RDB del Hito 7) |

## 3. Otras condiciones provocadas

### Timeout configurado demasiado bajo (`DEP_TIMEOUT_S=0.001`)

Una **segunda instancia** de la API con esa variable (la configuración normal no se tocó):

| Ruta (producto) | Normal (3,0 s) | Alterada (0,001 s) | Causa en el log (alterada) |
| :--- | :--- | :--- | :--- |
| `/partidos/F2030-001/eventos` (Neo4j) | 200 · 169 ms | **200** · 170 ms | — |
| `/equipos/ZZZ` (MongoDB) | 404 · 153 ms | **404** · 135 ms | — |
| `/sesiones/no-existe-h11` (Redis) | 404 · 55 ms | **404** · 87 ms | — |
| `/partidos/F2030-063/comentarios` (Cassandra) | 200 · 1.744 ms | **503** · 143 ms | `Unable to connect to any servers … OperationTimedOut` |
| `/partidos/F2030-018/estadisticas` (InfluxDB) | 503 (H6) · 20 ms | 503 · 4 ms | `HTTP 400` (H6 enmascara el timeout) |
| `/partidos/F2030-999/detalle` (IRIS) | 503 (H7) · 55 ms | **503** · 56 ms | `<COMMUNICATION LINK ERROR> Failed to connect to server` |

Lectura:

- **La API no distingue timeout de caída (RF18):** ambos salen como `503 DEPENDENCY_UNAVAILABLE`.
  Solo el log separa la causa.
- **En loopback, 1 ms puede alcanzar.** Neo4j y Mongo respondieron igual: sus timeouts limitan la
  conexión y el socket, no la operación completa, y en `localhost` conectar tarda menos de 1 ms.
  Redis respondió 404 en esta corrida, pero en una corrida anterior del mismo escenario dio 503
  (`Timeout reading from socket`): con 1 ms el resultado no es determinístico y no se debe usar
  como medida de rendimiento.

### Credencial ausente (InfluxDB sin `INFLUXDB3_TOKEN`)

| Instancia | Respuesta | Causa en el log |
| :--- | :--- | :--- |
| con token | `503` en 32 ms | `HTTP 400` (H6) |
| sin token | `503` en 17 ms | `falta INFLUXDB3_TOKEN en el entorno` |

Mismo status, mismo cuerpo y causas distintas. El token del Hito 8 no se regeneró ni se modificó.

## 4. Comportamiento de la API ante fallas (RF17, RF18, RNF12)

| Situación | Respuesta actual de la API (observada) | ¿Se distingue? | Propuesta |
| :--- | :--- | :---: | :--- |
| Ausencia válida (recurso inexistente) | `404` con `code` de dominio | sí | — |
| Respuesta vacía válida | `200` con lista vacía (Neo4j, Cassandra) | sí | Influx: hoy 503 por H6 |
| Error de validación | `400 VALIDATION_ERROR` sin tocar la base | sí | — |
| Dependencia caída (Redis detenido) | `503 DEPENDENCY_UNAVAILABLE` en < 30 ms | sí | — |
| Dependencia lenta / timeout | `503` (igual que caída) | **no** | `504 DEPENDENCY_TIMEOUT` |
| No autenticada (IRIS H3, token ausente) | `503` | **no** | `503` con `detalles.motivo = "autenticacion"` o un `code` propio; detalle técnico solo en el log |
| Contexto/modelo incorrecto (H1, H2, H5, H6, H7) | `404`, `500` o `503` según el caso | **no** | `500 INTERNAL_ERROR` (es un defecto de la aplicación, no una caída) |
| Error interno | `500` sin stack trace | sí | completar la correlación (H8) |
| API no alcanzable | sin respuesta HTTP (`connection refused`) | sí | — |

Lo que **sí** cumple hoy (RNF12): timeouts acotados en cada driver, ningún reintento infinito,
ninguna falla de dependencia oculta detrás de un 200, el detalle técnico solo en el log, y
aislamiento por ruta (Neo4j siguió en 200 con Redis caído).
