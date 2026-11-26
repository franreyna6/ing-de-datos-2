# Prueba de falla controlada 20261126-040222

Generado por `monitoreo/scripts/ejecutar_prueba_controlada.py`. Todos los valores salen de Prometheus (paso de 15 s) o del registro del cliente de carga; nada es estimado.

- Commit: `8dd15d7` · Inicio: 2026-11-26T04:10:10Z · Fin A: 2026-11-26T04:17:42Z
- Carga: 20 usuarios virtuales en lazo cerrado, pausa 0,1-0,3 s, mezcla de las 6 bases (ver `generar_carga.py`). Cache de comentarios: encendida (MISS y luego HIT).
- Fases de 150 s: normal → `docker stop fixture2030-redis` → `docker start fixture2030-redis`.
- Volumenes: ninguno se borro (RNF11). Escrituras solo en partidos de laboratorio `H13-20261126-040222-P1/P2`.

## A. Caida de Redis bajo carga

### Lo que vio Prometheus (promedio de cada fase, sin su primer minuto)

| Indicador | Normal | Falla (Redis detenido) | Recuperacion |
| :-- | --: | --: | --: |
| Requests/s de la API | 53.6 | 9.4 | 53.9 |
| Latencia p50 de la API | 3.8 ms | 1368.0 ms | 3.9 ms |
| Latencia p95 de la API | 1444.5 ms | 4684.8 ms | 1443.5 ms |
| Latencia p99 de la API | 2295.5 ms | 4937.0 ms | 2288.7 ms |
| p95 de GET comentarios | 10.1 ms | 4875.0 ms | 11.6 ms |
| p95 de llamadas a Redis | 2.4 ms | 2425.0 ms | 2.4 ms |
| p95 de llamadas a Cassandra | 24.3 ms | 24.2 ms | 24.3 ms |
| Lecturas que llegan a Cassandra (/s) | 1.2 | 3.7 | 1.1 |
| Aciertos de cache | 94.5 % | 0.0 % | 95.0 % |
| Tasa de errores 5xx | 12.0 % | 18.0 % | 11.9 % |
| redis_up (exporter, promedio) | 1.00 | 0.00 | 1.00 |

### Lo que vio el cliente de carga

| Fase | Requests | Requests/s | p50 | p95 | p99 | 5xx | Errores de conexion | Cache HIT/MISS |
| :-- | --: | --: | --: | --: | --: | --: | --: | :-- |
| normal | 8446 | 56.3 | 4.41 ms | 2044.45 ms | 2064.77 ms | 958 | 398 | 3020/172 |
| falla | 1526 | 10.2 | 41.72 ms | 4126.03 ms | 4141.25 ms | 256 | 64 | 11/567 |
| recuperacion | 8443 | 55.5 | 4.72 ms | 2041.53 ms | 2060.47 ms | 979 | 406 | 3043/167 |
| total | 18415 | 40.7 | 5.17 ms | 2058.45 ms | 4116.11 ms | 2193 | 868 | 6074/906 |

### Linea de tiempo de deteccion y recuperacion

Referencias: falla = `docker stop` a los +150 s; recuperacion = `docker start` a los +300 s. Resolucion de 15 s (intervalo de scrape y de evaluacion).

| Evento | Respecto de la falla | Respecto del docker start |
| :-- | --: | --: |
| redis_up = 0 (exporter) | +15 s | - |
| La API ve Redis no disponible | +30 s | - |
| redis_up = 1 de nuevo | +165 s | +15 s |
| La API ve Redis disponible de nuevo | +165 s | +15 s |
| Aciertos de cache < 80% | +30 s | - |
| Aciertos de cache >= 80% de nuevo | +180 s | +30 s |
| Alerta BaseNoDisponible redis pasa a firing | +105 s | - |
| Alerta CacheComentariosDegradada redis pasa a firing | +105 s | - |

### Alertas durante el experimento A

Tiempos relativos al `docker stop` de Redis. "Ya activa" = la alerta estaba disparada antes de empezar la carga (no la causo la prueba).

| Alerta | Estado | Componente | Origen | Severidad | Desde | Hasta |
| :-- | :-- | :-- | :-- | :-- | --: | --: |
| BaseNoDisponible | firing | iris | api-fixture | critica | ya activa | +345 s |
| LatenciaAPIp95SobreSLO | firing | api |  | advertencia | ya activa | -195 s |
| SondaExternaFallida | firing | cassandra | sonda-tcp | advertencia | ya activa | +345 s |
| SondaExternaFallida | firing | iris | sonda-tcp | advertencia | ya activa | +345 s |
| SondaExternaFallida | firing | mongodb | sonda-tcp | advertencia | ya activa | +345 s |
| SondaExternaFallida | firing | neo4j | sonda-tcp | advertencia | ya activa | +345 s |
| SondaExternaFallida | firing | redis | sonda-redis | advertencia | ya activa | +345 s |
| TargetDeMonitoreoCaido | firing | iris | iris | advertencia | ya activa | +345 s |
| LatenciaAPIp95SobreSLO | pending | api |  | advertencia | -105 s | -60 s |
| TasaErrores5xxAlta | pending | api |  | critica | -105 s | -60 s |
| LatenciaAPIp95SobreSLO | firing | api |  | advertencia | -45 s | +345 s |
| TasaErrores5xxAlta | firing | api |  | critica | -45 s | +345 s |
| BaseNoDisponible | pending | redis | api-fixture | critica | +45 s | +90 s |
| CacheComentariosDegradada | pending | redis |  | advertencia | +45 s | +90 s |
| BaseNoDisponible | firing | redis | api-fixture | critica | +105 s | +165 s |
| CacheComentariosDegradada | firing | redis |  | advertencia | +105 s | +180 s |

## B. Caida de Cassandra sin carga

- `docker stop fixture2030-cassandra` a las 2026-11-26T04:18:27Z (tardo 7 s).
- La API ve Cassandra no disponible: +20 s.
- Alerta `BaseNoDisponible{fuente="cassandra"}` en firing: +105 s (for: 1m + intervalo de chequeo de 15 s + evaluacion de 15 s).
- `docker start` a las 2026-11-26T04:20:26Z; la API la ve disponible +191 s y comentarios vuelve a 200 +166 s.

| Fuente | Ruta | Antes | Con Cassandra caida | Despues |
| :-- | :-- | :-- | :-- | :-- |
| cassandra | `/partidos/F2030-063/comentarios` | 200 | 503 DEPENDENCY_UNAVAILABLE | 200 |
| mongodb | `/equipos/ARG` | 404 NOT_FOUND | 404 NOT_FOUND | 404 NOT_FOUND |
| neo4j | `/partidos/F2030-001/eventos` | 200 | 200 | 200 |
| iris | `/partidos/F2030-001/detalle` | 503 DEPENDENCY_UNAVAILABLE | 503 DEPENDENCY_UNAVAILABLE | 503 DEPENDENCY_UNAVAILABLE |
| redis | `/sesiones/S0001` | 404 NOT_FOUND | 404 NOT_FOUND | 404 NOT_FOUND |

Alertas del experimento B (tiempos relativos al `docker stop` de Cassandra; "ya activa" = disparada antes de empezar B):

- BaseNoDisponible (iris, api-fixture, critica) firing desde ya activa hasta +338 s
- LatenciaAPIp95SobreSLO (api, , advertencia) firing desde ya activa hasta +53 s
- SondaExternaFallida (cassandra, sonda-tcp, advertencia) firing desde ya activa hasta +338 s
- SondaExternaFallida (iris, sonda-tcp, advertencia) firing desde ya activa hasta +338 s
- SondaExternaFallida (mongodb, sonda-tcp, advertencia) firing desde ya activa hasta +338 s
- SondaExternaFallida (neo4j, sonda-tcp, advertencia) firing desde ya activa hasta +338 s
- SondaExternaFallida (redis, sonda-redis, advertencia) firing desde ya activa hasta +338 s
- TargetDeMonitoreoCaido (iris, iris, advertencia) firing desde ya activa hasta +338 s
- TasaErrores5xxAlta (api, , critica) firing desde ya activa hasta +53 s
- BaseNoDisponible (cassandra, api-fixture, critica) pending desde +38 s hasta +83 s
- BaseNoDisponible (cassandra, api-fixture, critica) firing desde +98 s hasta +308 s
- LatenciaAPIp95SobreSLO (api, , advertencia) pending desde +143 s hasta +173 s
- TasaErrores5xxAlta (api, , critica) pending desde +143 s hasta +188 s
- TasaErrores5xxAlta (api, , critica) firing desde +203 s hasta +338 s

## Archivos de esta corrida

- `series_prometheus.csv`, `serie_cliente_5s.csv`, `alertas.json`, `metadata.json`
- `requests_cliente.csv.gz` (una fila por request)
- `alertmanager_durante_falla_*.json`, `experimento_b_cassandra.json`

Capturas del tablero (rango exacto de la prueba):

- `../../dashboards/prueba_20261126-040222_A_redis_tablero_completo.png`
- `../../dashboards/prueba_20261126-040222_A_redis_salud_infraestructura.png`
- `../../dashboards/prueba_20261126-040222_A_redis_salud_vista_api.png`
- `../../dashboards/prueba_20261126-040222_A_redis_throughput.png`
- `../../dashboards/prueba_20261126-040222_A_redis_latencia_api.png`
- `../../dashboards/prueba_20261126-040222_A_redis_errores.png`
- `../../dashboards/prueba_20261126-040222_A_redis_latencia_por_base.png`
- `../../dashboards/prueba_20261126-040222_A_redis_operaciones_por_base.png`
- `../../dashboards/prueba_20261126-040222_A_redis_cache.png`
- `../../dashboards/prueba_20261126-040222_A_redis_memoria_redis.png`
- `../../dashboards/prueba_20261126-040222_A_redis_escrituras_cassandra.png`
- `../../dashboards/prueba_20261126-040222_B_cassandra_tablero_completo.png`
- `../../dashboards/prueba_20261126-040222_B_cassandra_salud_infraestructura.png`
- `../../dashboards/prueba_20261126-040222_B_cassandra_salud_vista_api.png`
- `../../dashboards/prueba_20261126-040222_B_cassandra_throughput.png`
- `../../dashboards/prueba_20261126-040222_B_cassandra_latencia_api.png`
- `../../dashboards/prueba_20261126-040222_B_cassandra_errores.png`
- `../../dashboards/prueba_20261126-040222_B_cassandra_latencia_por_base.png`
- `../../dashboards/prueba_20261126-040222_B_cassandra_operaciones_por_base.png`
- `../../dashboards/prueba_20261126-040222_B_cassandra_cache.png`
- `../../dashboards/prueba_20261126-040222_B_cassandra_memoria_redis.png`
- `../../dashboards/prueba_20261126-040222_B_cassandra_escrituras_cassandra.png`

## Limites de esta medicion

- Una sola maquina (Docker Desktop): bases, API, monitoreo y generador de carga comparten CPU.
- Resolucion de 15 s: los tiempos de deteccion tienen un error de hasta un intervalo.
- Los percentiles de Prometheus salen de buckets de histograma (aproximados); los del cliente son exactos.
