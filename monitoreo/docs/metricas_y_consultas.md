# Métricas y consultas PromQL (RF4, RF8, RNF3, RNF4)

## 1. Qué se mide directamente, qué viene de un exporter y qué se infiere (RNF3)

| Origen | Cómo se obtiene | Ejemplos | Grado de confianza |
| :--- | :--- | :--- | :--- |
| **Medido directamente** (instrumentación propia) | La API cuenta y cronometra cada request y cada llamada a una base, en el mismo proceso que la atiende | `fixture_api_requests_total`, `fixture_api_request_duration_seconds`, `fixture_dependencia_duration_seconds`, `fixture_cache_comentarios_total`, `fixture_comentarios_creados_total` | Alto: es el tiempo real de cada operación, sin red de por medio. No incluye la cola ni la red del cliente; para eso está el registro del generador de carga. |
| **Chequeo activo** (instrumentación propia) | Un hilo de la API ejecuta cada 15 s el chequeo de protocolo de `/salud` para cada base | `fixture_dependencia_disponible`, `fixture_dependencia_chequeo_seconds` | Alto para "la base responde consultas". Resolución de 15 s. |
| **Exporter** (traductor) | Un proceso aparte consulta la base con su protocolo (INFO, serverStatus) y lo traduce a métricas | `redis_up`, `redis_memory_used_bytes`, `redis_keyspace_hits_total`, `mongodb_up`, opcounters | Alto, pero es la visión de la base: no sabe qué ruta de la API generó la carga. |
| **Endpoint nativo** | La base expone `/metrics` propio | InfluxDB 3 (`/metrics`, con token), IRIS (`/api/monitor/metrics`) | Alto. |
| **Sonda externa** | blackbox_exporter abre una conexión (TCP, PING, HTTP) | `probe_success`, `probe_duration_seconds` | Medio: TCP solo prueba que el puerto acepta conexiones. |
| **Generado por Prometheus** | En cada scrape | `up`, `scrape_duration_seconds`, `scrape_samples_scraped`, `ALERTS` | Alto: dice si se pudo *medir*, no si la base funciona. |
| **Inferido o propuesto** | No se mide en el laboratorio | Latencia entre regiones, lag de réplicas, comportamiento con 2-3 M de usuarios, métricas JMX de Cassandra, métricas internas de Neo4j | Ver [`limitaciones_y_evidencia.md`](limitaciones_y_evidencia.md): se declara como propuesta, nunca como observado. |

**Métricas de aplicación y de infraestructura no se mezclan (RF4).** Las de aplicación empiezan con `fixture_` y salen del job `api-fixture` (`capa=aplicacion`). Las de infraestructura salen de exporters o endpoints nativos (`capa=infraestructura`). Así, ante un aumento de latencia se puede ver si el tiempo extra está *dentro de la API* o *dentro de la base*.

## 2. Tipos de métrica usados (Clase 14)

| Tipo | Definición (Clase 14) | Métricas del Fixture |
| :--- | :--- | :--- |
| **Counter** | Solo sube (o vuelve a cero). Acumulativo. | `fixture_api_requests_total`, `fixture_comentarios_creados_total`, `fixture_cache_comentarios_total`, `redis_keyspace_hits_total` |
| **Gauge** | Sube y baja. Valor instantáneo. | `fixture_dependencia_disponible`, `redis_memory_used_bytes`, `probe_success`, `up` |
| **Histogram** | Mide duraciones y las agrupa en *buckets*. | `fixture_api_request_duration_seconds`, `fixture_dependencia_duration_seconds` |
| **Summary** | Como el histograma, pero con cuantiles exactos calculados en el cliente. | **No se usa.** Los cuantiles de un Summary no se pueden agregar entre series. Con histogramas, el p95 se calcula en Prometheus para cualquier combinación de etiquetas (por ruta, por base, total). |

Buckets de los histogramas, en segundos: 0,0025 · 0,005 · 0,01 · 0,025 · 0,05 · 0,1 · 0,25 · 0,5 · 1 · 2,5 · 5 · 10. Cubren desde una lectura cacheada del Hito 12 (p50 de unos 3 ms) hasta más allá del timeout de 3 s de las dependencias. Los percentiles que da `histogram_quantile` son **aproximados**: se interpolan dentro del bucket.

## 3. Catálogo de métricas propias (`/metrics` de la API)

| Métrica | Tipo | Etiquetas | Qué significa |
| :--- | :--- | :--- | :--- |
| `fixture_api_requests_total` | counter | `metodo`, `ruta`, `estado` | Requests atendidas. `ruta` es la **plantilla** (`/partidos/{codigo}/comentarios`), nunca la URL real; las URLs inexistentes se agrupan en `sin_ruta`. |
| `fixture_api_request_duration_seconds` | histogram | `metodo`, `ruta` | Tiempo de respuesta dentro de la API. Es el mismo valor que el header `X-Duracion-ms` del Hito 12. |
| `fixture_dependencia_duration_seconds` | histogram | `fuente`, `operacion`, `resultado` | Duración de cada llamada a un adaptador (`obtener_equipo`, `leer_comentarios`, `cache_leer`...). `resultado`: `ok`; `error` = terminó en excepción; `cortocircuito` = no se intentó porque la base había fallado hace poco. |
| `fixture_dependencia_disponible` | gauge | `fuente` | 1 o 0 según el chequeo de protocolo de cada adaptador, cada 15 s. |
| `fixture_dependencia_chequeo_seconds` | gauge | `fuente` | Cuánto tardó el último chequeo. |
| `fixture_cache_comentarios_total` | counter | `estado` (OFF, MISS, HIT) | Resultado de la caché de comentarios del Hito 12 en cada lectura. |
| `fixture_cortocircuito_abierto` | gauge | `fuente` | 1 si el corte rápido de esa base está abierto (falló hace menos de `CORTOCIRCUITO_S` segundos). Ver [`limitaciones_y_evidencia.md`](limitaciones_y_evidencia.md), mejora transversal. |
| `fixture_cortocircuito_rechazos_total` | counter | `fuente` | Llamadas que la API no intentó por tener el corte abierto: respondió 503 o leyó sin caché al instante. |
| `fixture_comentarios_creados_total` | counter | `partido` | Escrituras confirmadas en Cassandra. `partido` solo acepta códigos `F2030-NNN` o de laboratorio `H12-`/`H13-`; cualquier otro valor se agrupa en `otro`. |

**Integridad (RNF5).** Instrumentar no cambia ningún dato: los contadores viven en memoria y `/metrics` solo los lee. El código de los adaptadores no se modificó: se envolvieron sus métodos en `app/main.py` (`metricas.instrumentar_adaptador`). Los 22 tests de la API pasan: los 9 del Hito 10, 8 de métricas (`tests/test_metricas.py`) y 5 del corte rápido (`tests/test_cortocircuito.py`).

**Cardinalidad.** Cada etiqueta tiene un conjunto acotado de valores: alrededor de una docena de plantillas de ruta (las 8 rutas de negocio, `/salud`, las de la documentación y `sin_ruta`), 6 fuentes, unos 10 códigos HTTP, 3 estados de caché y los partidos del fixture. Es la misma disciplina que se aplicó a los tags del Hito 8: un identificador libre como etiqueta multiplica las series sin aportar una consulta.

## 4. Consultas PromQL documentadas (RF8)

Todas están en el tablero y las ejecuta `scripts/verificar_targets.py`, que guarda su resultado en [`../evidencia/prometheus_targets.md`](../evidencia/prometheus_targets.md). `rate(x[1m])` es el aumento por segundo del contador `x` promediado en el último minuto. Una ventana de 1 minuto con scrape de 15 s usa 4 muestras: alcanza para seguir una prueba de pocos minutos sin tapar los cambios.

### Q2 — Throughput de la API

```promql
sum(rate(fixture_api_requests_total[1m]))
```

- **Qué mide:** requests por segundo que atiende la API, todas las rutas.
- **Unidad:** requests/s. **Ventana:** 1 minuto.
- Con `sum by (ruta)` se separa por ruta (panel *Throughput*).

### Q3 — Latencia p95 de la API (SLI del SLO)

```promql
histogram_quantile(0.95, sum by (le) (rate(fixture_api_request_duration_seconds_bucket[1m])))
```

- **Qué mide:** el tiempo por debajo del cual quedó el 95 % de las requests del último minuto.
- **Unidad:** segundos. **Ventana:** 1 minuto.
- Es la forma de la Clase 14 (*"latencia del 95% de los usuarios"*). El `sum by (le)` suma los buckets de todas las rutas antes de calcular el cuantil; por eso hace falta un histograma y no un summary.

### Q4 — Tasa de errores 5xx

```promql
sum(rate(fixture_api_requests_total{estado=~"5.."}[1m])) / sum(rate(fixture_api_requests_total[1m]))
```

- **Qué mide:** proporción de requests que terminaron en error del servidor (un 503 es una base caída).
- **Unidad:** proporción de 0 a 1 (el tablero la muestra en %). **Ventana:** 1 minuto.
- No cuenta los 4xx: un 404 es una respuesta correcta de "no existe" y un 400 es un pedido inválido.

### Q5 — Latencia p95 por base (comparación entre bases, RF7)

```promql
histogram_quantile(0.95, sum by (le, fuente) (rate(fixture_dependencia_duration_seconds_bucket[1m])))
```

- **Qué mide:** el p95 de las llamadas de la API a cada base.
- **Unidad:** segundos. **Ventana:** 1 minuto.
- Responde *"¿cómo distinguen que el problema está en la API y no en la base?"*. Si Q3 sube y Q5 de una fuente sube igual, la base es la lenta. Si Q3 sube y ninguna fuente sube, el tiempo se va en la API (hilos, serialización, cola).

### Q6 — Disponibilidad por base, vista por la API

```promql
fixture_dependencia_disponible
```

- **Qué mide:** 1 si la base respondió al chequeo de protocolo, 0 si no.
- **Unidad:** 1/0. **Ventana:** instantánea (se actualiza cada 15 s).

### Q7 — Tasa de aciertos de la caché de comentarios

```promql
sum(rate(fixture_cache_comentarios_total{estado="HIT"}[1m]))
  / sum(rate(fixture_cache_comentarios_total{estado=~"HIT|MISS"}[1m]))
```

- **Qué mide:** qué fracción de las lecturas de comentarios se resolvió en Redis sin ir a Cassandra.
- **Unidad:** proporción de 0 a 1. **Ventana:** 1 minuto.
- En el Hito 12 fue 0,98.

### Q8 — Memoria de Redis usada contra la máxima

```promql
redis_memory_used_bytes / redis_memory_max_bytes
```

- **Qué mide:** qué tan cerca está Redis de `maxmemory 100mb`. A partir de ahí, `volatile-lru` empieza a desalojar claves con TTL.
- **Unidad:** proporción de 0 a 1. **Ventana:** instantánea.

### Q1, Q9 y Q10

| Consulta | PromQL | Qué mide | Unidad y ventana |
| :--- | :--- | :--- | :--- |
| Q1 | `up` | Si Prometheus pudo leer cada target | 1/0, instantánea |
| Q9 | `probe_success` | Si cada base aceptó la conexión de la sonda externa | 1/0, instantánea |
| Q10 | `sum by (partido) (rate(fixture_comentarios_creados_total[1m]))` | Escrituras de comentarios en Cassandra por partido (panel de la Clase 14) | escrituras/s, 1 minuto |

## 5. Cómo se relacionan las métricas con los objetivos del TPO (RF11)

| Objetivo del TPO | Métrica que lo observa | Qué se puede afirmar con el laboratorio |
| :--- | :--- | :--- |
| **Concurrencia** | Usuarios virtuales del generador; `rate(fixture_api_requests_total[1m])` | Comportamiento con 20 usuarios en lazo cerrado en una máquina. No equivale a 2-3 M de usuarios. |
| **Throughput** | Q2, Q10, operaciones por base | Requests/s y escrituras/s medidos. |
| **Latencia** (p95 < 100 ms, Hito 1) | Q3, Q5 y la latencia del cliente | p95 medido dentro de la API y en el cliente, por fase. |
| **Disponibilidad** (99,99 %, Hito 1) | Q1, Q6, Q9 y las alertas `BaseNoDisponible` / `SondaExternaFallida` | Tiempo de detección de una caída y qué rutas siguen funcionando. **No** se mide un porcentaje de uptime anual. |
| **Distribución** | Comparación por base (Q5, operaciones por fuente), escrituras por partido | Cómo se reparte el trabajo entre bases y partidos. La distribución entre nodos y regiones **no** existe en el laboratorio. |
| **Recuperación** | Tiempo entre `docker start` y la vuelta de Q6 a 1; Q7 volviendo a su nivel | Tiempo de recuperación medido en la prueba controlada. |

Los valores medidos están en [`limitaciones_y_evidencia.md`](limitaciones_y_evidencia.md) y en el informe de la prueba (`../evidencia/prueba_de_falla/<etiqueta>/resumen.md`).
