# Inventario de componentes monitoreados (sección 5.1, RF2, RF3)

Una base figura como **monitoreada** solo si hay un target, un exporter, un endpoint o una consulta que lo respalde. Estar en el diagrama no alcanza. La última verificación real de cada fila está en [`../evidencia/prometheus_targets.md`](../evidencia/prometheus_targets.md), generada por `scripts/verificar_targets.py`.

## Cómo se observa cada componente

Hay tres capas de observación, que responden preguntas distintas (Clase 14: monitoreo = *si* algo falla; observabilidad = *por qué*):

| Capa | Mecanismo | Qué responde |
| :--- | :--- | :--- |
| **Aplicación** | `/metrics` de la API, instrumentada en este hito | ¿Cómo viven el uso las rutas y cada base *desde la API*? Latencia, throughput y errores por ruta y por fuente, caché, escrituras por partido. |
| **Infraestructura** | Exporters (Redis, MongoDB) y endpoints nativos (InfluxDB, IRIS) | ¿Cómo está el motor por dentro? Memoria, operaciones, aciertos de caché. |
| **Sonda externa** | blackbox_exporter: TCP, PING de Redis, HTTP | ¿La base acepta conexiones desde afuera, como lo haría un cliente? |

## Inventario

| Componente | Modelo de datos | Función en el Fixture | Puerto / endpoint | Mecanismo de monitoreo (job) | Métricas seleccionadas | Riesgo que se intenta observar | Limitaciones del monitoreo |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **API integrada** (Hito 10) | — (integra las 6 fuentes) | Única puerta de entrada de las aplicaciones al Fixture | `127.0.0.1:8000/metrics` | Instrumentación propia con `prometheus_client` (`api-fixture`) | `fixture_api_requests_total`, `fixture_api_request_duration_seconds`, `fixture_dependencia_duration_seconds`, `fixture_dependencia_disponible`, `fixture_cache_comentarios_total`, `fixture_comentarios_creados_total`, `fixture_cortocircuito_*` | Latencia fuera del SLO, errores 5xx, una base lenta que arrastra a la API | Los contadores viven en memoria y se reinician con la API; `rate()` lo tolera. Un solo proceso: no se agregan réplicas de la API. |
| **MongoDB** (Hito 4) | Documental | Equipos y jugadores (ficha, plantel) | `27017` | `mongodb_exporter` (`mongodb`, `:9216`) + sonda TCP (`sonda-tcp`) + chequeo de la API | `mongodb_up`, opcounters por tipo, conexiones | Caída del nodo, saturación de operaciones | Monoinstancia: no hay métricas de replica set (lag, elecciones), porque el replica set no existe en el laboratorio. |
| **Neo4j** (Hito 5) | Grafo | Partidos, sedes, eventos y sus relaciones | `7474` HTTP, `7687` Bolt | Sonda HTTP a `7474` y TCP a `7687` (`sonda-http`, `sonda-tcp`) + chequeo de la API (consulta mínima por Bolt) + duración de `eventos_de_partido` | `probe_success`, `probe_duration_seconds`, `fixture_dependencia_*{fuente="neo4j"}` | Caída, recorridos lentos | El endpoint Prometheus de Neo4j es de la edición Enterprise; con Community no hay métricas internas (heap, page cache, transacciones). Se mide desde afuera y desde la API. |
| **Cassandra** (Hito 6) | Tabular / columnar | Comentarios masivos por partido y ventana | `9042` CQL | Sonda TCP (`sonda-tcp`) + chequeo de la API (`SELECT release_version`) + duración de lecturas y escrituras + escrituras por partido | `probe_success`, `fixture_dependencia_disponible{fuente="cassandra"}`, `fixture_dependencia_duration_seconds{fuente="cassandra"}`, `fixture_comentarios_creados_total` | Nodo caído (alerta crítica), partición caliente en un pico de gol | Sin exporter JMX: no hay métricas internas (compaction, pending tasks, latencia por tabla). La sonda TCP solo prueba el puerto; Docker Desktop puede aceptar la conexión aunque el nodo no esté listo. Por eso la señal de disponibilidad confiable es el chequeo de la API. |
| **Redis** (Hito 7) | Clave/valor | Sesiones y caché de comentarios (Hito 12) | `6379` | `redis_exporter` (`redis`, `:9121`) + sonda PING/PONG (`sonda-redis`) + chequeo de la API | `redis_up`, `redis_memory_used_bytes / redis_memory_max_bytes`, `redis_keyspace_hits_total`, `redis_keyspace_misses_total`, `redis_evicted_keys_total` | Memoria cerca de `maxmemory` (con `volatile-lru`), caída de la caché | Monoinstancia: no hay métricas de réplica ni de Sentinel. |
| **InfluxDB 3 Core** (Hito 8) | Series temporales | Estadísticas en vivo por partido | `8181` HTTP | Endpoint nativo `/metrics` con token (`influxdb`) + sonda HTTP a `/health` (`sonda-http`) + duración de `estadisticas` | `up{job="influxdb"}`, métricas internas expuestas por el servidor, `fixture_dependencia_*{fuente="influxdb"}` | Caída, consultas temporales lentas | Necesita el token del Hito 8. Si falta, el target queda DOWN con 401 y se documenta, sin inventar un token. La sonda acepta 401 como "servidor vivo". |
| **IRIS** (Hito 9) | Objetos persistentes | Partido como entidad compleja (estado, eventos, terna) | `52773` HTTP, `1972` superserver | Endpoint nativo `/api/monitor/metrics` (`iris`) + sonda TCP a `1972` + duración de `detalle_partido` | `up{job="iris"}`, `iris_glo_ref_per_sec`, `iris_cpu_usage`, `fixture_dependencia_*{fuente="iris"}` | Caída, carga de la instancia | La ruta `/api/monitor` debe estar habilitada en la instancia (lo está por defecto en Community). |
| **Prometheus** | — | Recolección y reglas de alerta | `127.0.0.1:9090` | Se observa a sí mismo (`prometheus`) | `up`, `scrape_duration_seconds`, `scrape_samples_scraped` | Que el propio monitoreo deje de leer un target | Retención de 7 días, un solo nodo (sin alta disponibilidad del monitoreo). |
| **Alertmanager** | — | Recibe, agrupa e inhibe alertas | `127.0.0.1:9093` | Verificado por `verificar_targets.py` (`/-/ready`) | Alertas recibidas (API v2) | — | Sin canales de notificación reales en el laboratorio (no hay credenciales de mail ni de chat). |
| **Grafana** | — | Visualización (tablero War Room) | `127.0.0.1:3000` | Verificado por `verificar_targets.py` (`/api/health`) | — | — | No guarda métricas: si Prometheus cae, el tablero queda vacío. |

## Relación entre cada job y el componente observado

| Job de Prometheus | Componente | Etiquetas fijas |
| :--- | :--- | :--- |
| `api-fixture` | API (Hito 10) | `capa=aplicacion`, `mecanismo=instrumentacion_propia` |
| `mongodb` | MongoDB | `modelo=documental`, `hito=4`, `mecanismo=exporter` |
| `redis` | Redis | `modelo=clave-valor`, `hito=7`, `mecanismo=exporter` |
| `influxdb` | InfluxDB | `modelo=series-temporales`, `hito=8`, `mecanismo=endpoint_nativo` |
| `iris` | IRIS | `modelo=objetos`, `hito=9`, `mecanismo=endpoint_nativo` |
| `sonda-tcp` | Cassandra, MongoDB, Neo4j, IRIS | `mecanismo=sonda_blackbox` y el `componente` de cada destino |
| `sonda-redis` | Redis | ídem |
| `sonda-http` | Neo4j, InfluxDB | ídem |
| `prometheus` | Prometheus | `capa=monitoreo` |

Con la etiqueta `componente` se cruza cualquier métrica con su base. Por ejemplo, `probe_success{componente="cassandra"}` y `fixture_dependencia_disponible{fuente="cassandra"}` son la vista externa y la vista de la API sobre el mismo nodo.

## Cobertura de RF3 (disponibilidad de al menos tres componentes)

Hay métricas de disponibilidad de **las seis bases y de la API**, cada una por al menos dos caminos independientes:

| Componente | Señal 1 | Señal 2 | Señal 3 |
| :--- | :--- | :--- | :--- |
| MongoDB | `mongodb_up` (exporter) | `probe_success` (TCP) | `fixture_dependencia_disponible` (API) |
| Neo4j | `probe_success` (HTTP) | `probe_success` (TCP) | `fixture_dependencia_disponible` (API) |
| Cassandra | `probe_success` (TCP) | `fixture_dependencia_disponible` (API) | — |
| Redis | `redis_up` (exporter) | `probe_success` (PING) | `fixture_dependencia_disponible` (API) |
| InfluxDB | `up{job="influxdb"}` (nativo) | `probe_success` (HTTP) | `fixture_dependencia_disponible` (API) |
| IRIS | `up{job="iris"}` (nativo) | `probe_success` (TCP) | `fixture_dependencia_disponible` (API) |
| API | `up{job="api-fixture"}` | — | — |
