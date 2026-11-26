# Prueba de falla controlada 20261126-054628

Generado por `monitoreo/scripts/ejecutar_prueba_controlada.py`. Todos los valores salen de Prometheus (paso de 15 s) o del registro del cliente de carga; nada es estimado.

- Commit: `85e91ae` · Inicio: 2026-11-26T05:51:37Z · Fin A: 2026-11-26T05:59:07Z
- Carga: 20 usuarios virtuales en lazo cerrado, pausa 0,1-0,3 s, mezcla de las 6 bases (ver `generar_carga.py`). Cache de comentarios: encendida (MISS y luego HIT). Corte rapido de la API (CORTOCIRCUITO_S): 10.
- Fases de 150 s: normal → `docker stop fixture2030-redis` → `docker start fixture2030-redis`.
- Volumenes: ninguno se borro (RNF11). Escrituras solo en partidos de laboratorio `H13-20261126-054628-P1/P2`.

## A. Caida de Redis bajo carga

### Lo que vio Prometheus (promedio de cada fase, sin su primer minuto)

| Indicador | Normal | Falla (Redis detenido) | Recuperacion |
| :-- | --: | --: | --: |
| Requests/s de la API | 92.1 | 88.5 | 91.1 |
| Latencia p50 de la API | 4.5 ms | 10.4 ms | 4.9 ms |
| Latencia p95 de la API | 23.7 ms | 32.8 ms | 26.9 ms |
| Latencia p99 de la API | 43.3 ms | 62.5 ms | 48.2 ms |
| p95 de GET comentarios | 9.7 ms | 24.9 ms | 14.5 ms |
| p95 de llamadas a Redis | 2.5 ms | 2.4 ms | 3.6 ms |
| p95 de llamadas a Cassandra | 24.2 ms | 24.2 ms | 24.3 ms |
| Lecturas que llegan a Cassandra (/s) | 1.4 | 35.5 | 1.4 |
| Aciertos de cache | 96.2 % | 0.0 % | 96.2 % |
| Tasa de errores 5xx | 0.0 % | 5.0 % | 0.0 % |
| Llamadas a Redis evitadas por el corte rapido (/s) | - | 75.3 | 0.0 |
| redis_up (exporter, promedio) | 1.00 | 0.00 | 1.00 |

### Lo que vio el cliente de carga

| Fase | Requests | Requests/s | p50 | p95 | p99 | 5xx | Errores de conexion | Cache HIT/MISS |
| :-- | --: | --: | --: | --: | --: | --: | --: | :-- |
| normal | 13758 | 91.7 | 5.53 ms | 24.03 ms | 36.26 ms | 0 | 0 | 5222/204 |
| falla | 13318 | 88.8 | 12.13 ms | 29.85 ms | 56.08 ms | 673 | 0 | 12/5315 |
| recuperacion | 13697 | 91.3 | 6.08 ms | 26.88 ms | 45.28 ms | 2 | 0 | 5192/244 |
| total | 40773 | 90.6 | 6.66 ms | 26.75 ms | 46.12 ms | 675 | 0 | 10426/5763 |

### Linea de tiempo de deteccion y recuperacion

Referencias: falla = `docker stop` a los +150 s; recuperacion = `docker start` a los +300 s. Resolucion de 15 s (intervalo de scrape y de evaluacion).

| Evento | Respecto de la falla | Respecto del docker start |
| :-- | --: | --: |
| redis_up = 0 (exporter) | +15 s | - |
| La API ve Redis no disponible | +15 s | - |
| redis_up = 1 de nuevo | +165 s | +15 s |
| La API ve Redis disponible de nuevo | +165 s | +15 s |
| Aciertos de cache < 80% | +15 s | - |
| Aciertos de cache >= 80% de nuevo | +195 s | +45 s |
| Alerta SondaExternaFallida redis pasa a firing | +75 s | - |
| Alerta BaseNoDisponible redis pasa a firing | +90 s | - |
| Alerta CacheComentariosDegradada redis pasa a firing | +90 s | - |
| Alerta TasaErrores5xxAlta api pasa a firing | +105 s | - |

### Alertas durante el experimento A

Tiempos relativos al `docker stop` de Redis. "Ya activa" = la alerta estaba disparada antes de empezar la carga (no la causo la prueba).

| Alerta | Estado | Componente | Origen | Severidad | Desde | Hasta |
| :-- | :-- | :-- | :-- | :-- | --: | --: |
| SondaExternaFallida | pending | redis | sonda-redis | advertencia | +15 s | +60 s |
| BaseNoDisponible | pending | redis | api-fixture | critica | +30 s | +75 s |
| CacheComentariosDegradada | pending | redis |  | advertencia | +30 s | +75 s |
| TasaErrores5xxAlta | pending | api |  | critica | +45 s | +90 s |
| SondaExternaFallida | firing | redis | sonda-redis | advertencia | +75 s | +165 s |
| BaseNoDisponible | firing | redis | api-fixture | critica | +90 s | +165 s |
| CacheComentariosDegradada | firing | redis |  | advertencia | +90 s | +195 s |
| TasaErrores5xxAlta | firing | api |  | critica | +105 s | +195 s |

## B. Caida de Cassandra sin carga

- `docker stop fixture2030-cassandra` a las 2026-11-26T05:59:53Z (tardo 5 s).
- La API ve Cassandra no disponible: +10 s.
- Alerta `BaseNoDisponible{fuente="cassandra"}` en firing: +100 s (for: 1m + intervalo de chequeo de 15 s + evaluacion de 15 s).
- `docker start` a las 2026-11-26T06:01:43Z; la API la ve disponible +56 s y comentarios vuelve a 200 +41 s.

| Fuente | Ruta | Antes | Con Cassandra caida | Despues |
| :-- | :-- | :-- | :-- | :-- |
| cassandra | `/partidos/F2030-063/comentarios` | 200 | 503 DEPENDENCY_UNAVAILABLE | 200 |
| mongodb | `/equipos/ARG` | 200 | 200 | 200 |
| neo4j | `/partidos/F2030-001/eventos` | 200 | 200 | 200 |
| iris | `/partidos/F2030-001/detalle` | 200 | 200 | 200 |
| redis | `/sesiones/S0001` | 404 NOT_FOUND | 404 NOT_FOUND | 404 NOT_FOUND |

Alertas del experimento B (tiempos relativos al `docker stop` de Cassandra; "ya activa" = disparada antes de empezar B):

- SondaExternaFallida (cassandra, sonda-tcp, advertencia) pending desde +10 s hasta +55 s
- BaseNoDisponible (cassandra, api-fixture, critica) pending desde +25 s hasta +70 s
- SondaExternaFallida (cassandra, sonda-tcp, advertencia) firing desde +70 s hasta +100 s
- BaseNoDisponible (cassandra, api-fixture, critica) firing desde +85 s hasta +160 s
- TasaErrores5xxAlta (api, , critica) pending desde +145 s hasta +205 s

## Archivos de esta corrida

- `series_prometheus.csv`, `serie_cliente_5s.csv`, `alertas.json`, `metadata.json`
- `requests_cliente.csv.gz` (una fila por request)
- `alertmanager_durante_falla_*.json`, `experimento_b_cassandra.json`

Capturas del tablero (rango exacto de la prueba):

- `../../dashboards/prueba_20261126-054628_A_redis_tablero_completo.png`
- `../../dashboards/prueba_20261126-054628_A_redis_salud_infraestructura.png`
- `../../dashboards/prueba_20261126-054628_A_redis_salud_vista_api.png`
- `../../dashboards/prueba_20261126-054628_A_redis_throughput.png`
- `../../dashboards/prueba_20261126-054628_A_redis_latencia_api.png`
- `../../dashboards/prueba_20261126-054628_A_redis_errores.png`
- `../../dashboards/prueba_20261126-054628_A_redis_latencia_por_base.png`
- `../../dashboards/prueba_20261126-054628_A_redis_operaciones_por_base.png`
- `../../dashboards/prueba_20261126-054628_A_redis_cache.png`
- `../../dashboards/prueba_20261126-054628_A_redis_memoria_redis.png`
- `../../dashboards/prueba_20261126-054628_A_redis_escrituras_cassandra.png`
- `../../dashboards/prueba_20261126-054628_A_redis_corte_rapido.png`
- `../../dashboards/prueba_20261126-054628_B_cassandra_tablero_completo.png`
- `../../dashboards/prueba_20261126-054628_B_cassandra_salud_infraestructura.png`
- `../../dashboards/prueba_20261126-054628_B_cassandra_salud_vista_api.png`
- `../../dashboards/prueba_20261126-054628_B_cassandra_throughput.png`
- `../../dashboards/prueba_20261126-054628_B_cassandra_latencia_api.png`
- `../../dashboards/prueba_20261126-054628_B_cassandra_errores.png`
- `../../dashboards/prueba_20261126-054628_B_cassandra_latencia_por_base.png`
- `../../dashboards/prueba_20261126-054628_B_cassandra_operaciones_por_base.png`
- `../../dashboards/prueba_20261126-054628_B_cassandra_cache.png`
- `../../dashboards/prueba_20261126-054628_B_cassandra_memoria_redis.png`
- `../../dashboards/prueba_20261126-054628_B_cassandra_escrituras_cassandra.png`
- `../../dashboards/prueba_20261126-054628_B_cassandra_corte_rapido.png`

## Limites de esta medicion

- Una sola maquina (Docker Desktop): bases, API, monitoreo y generador de carga comparten CPU.
- Resolucion de 15 s: los tiempos de deteccion tienen un error de hasta un intervalo.
- Los percentiles de Prometheus salen de buckets de histograma (aproximados); los del cliente son exactos.
