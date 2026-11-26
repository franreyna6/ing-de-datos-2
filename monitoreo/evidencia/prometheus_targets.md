# Verificacion de targets de Prometheus

- Fecha (UTC): 2026-11-26T06:06:20Z
- Commit: `85e91ae` (rama main, con cambios sin commitear en api/ o monitoreo/)
- Generado por: `monitoreo/scripts/verificar_targets.py`
- Resultado: **13 UP / 0 DOWN / 0 sondas que fallan** de 13 targets

En los jobs `sonda-*`, *Estado* es el del blackbox_exporter y *Sonda* dice si la base acepto la conexion (`probe_success`).

## Targets

| Job | Componente | Capa | Mecanismo | Instancia | Estado | Sonda | Ultimo scrape (s) | Ultimo error |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | --: | :-- |
| api-fixture | api | aplicacion | instrumentacion_propia | `host.docker.internal:8000` | UP | - | 0.0099 | - |
| influxdb | influxdb | infraestructura | endpoint_nativo | `host.docker.internal:8181` | UP | - | 0.0179 | - |
| iris | iris | infraestructura | endpoint_nativo | `fixture2030-iris:52773` | UP | - | 0.0359 | - |
| mongodb | mongodb | infraestructura | exporter | `mongodb-exporter:9216` | UP | - | 0.1355 | - |
| redis | redis | infraestructura | exporter | `redis-exporter:9121` | UP | - | 0.0189 | - |
| sonda-http | neo4j | infraestructura | sonda_blackbox | `http://host.docker.internal:7474/` | UP | OK | 0.0069 | - |
| sonda-http | influxdb | infraestructura | sonda_blackbox | `http://host.docker.internal:8181/health` | UP | OK | 0.0054 | - |
| sonda-redis | redis | infraestructura | sonda_blackbox | `host.docker.internal:6379` | UP | OK | 0.0059 | - |
| sonda-tcp | iris | infraestructura | sonda_blackbox | `host.docker.internal:1972` | UP | OK | 0.0033 | - |
| sonda-tcp | mongodb | infraestructura | sonda_blackbox | `host.docker.internal:27017` | UP | OK | 0.0029 | - |
| sonda-tcp | neo4j | infraestructura | sonda_blackbox | `host.docker.internal:7687` | UP | OK | 0.0032 | - |
| sonda-tcp | cassandra | infraestructura | sonda_blackbox | `host.docker.internal:9042` | UP | OK | 0.0033 | - |
| prometheus | prometheus | monitoreo | endpoint_nativo | `localhost:9090` | UP | - | 0.0043 | - |

## Metricas expuestas por job

| Job | Cantidad | Ejemplos |
| :-- | --: | :-- |
| api-fixture | 24 | ALERTS, ALERTS_FOR_STATE, fixture_api_request_duration_seconds_bucket, fixture_api_request_duration_seconds_count, fixture_api_request_duration_seconds_sum, fixture_api_requests_total, fixture_cache_comentarios_total, fixture_comentarios_creados_total |
| influxdb | 138 | datafusion_mem_pool_bytes, http_request_duration_seconds_bucket, http_request_duration_seconds_count, http_request_duration_seconds_sum, http_requests_total, http_response_body_size_bytes_bucket, http_response_body_size_bytes_count, http_response_body_size_bytes_sum |
| iris | 124 | ALERTS, ALERTS_FOR_STATE, iris_cache_efficiency, iris_cached_query_by_ns, iris_cpu_pct, iris_cpu_usage, iris_csp_activity, iris_csp_actual_connections |
| mongodb | 2495 | collector_scrape_time_ms, mongodb_asserts_total, mongodb_connections, mongodb_currentop_query_uptime, mongodb_dbstats_avgObjSize, mongodb_dbstats_collections, mongodb_dbstats_dataSize, mongodb_dbstats_freeStorageSize |
| prometheus | 293 | net_conntrack_dialer_conn_attempted_total, net_conntrack_dialer_conn_closed_total, net_conntrack_dialer_conn_established_total, net_conntrack_dialer_conn_failed_total, net_conntrack_listener_conn_accepted_total, net_conntrack_listener_conn_closed_total, prometheus_api_remote_read_queries, prometheus_build_info |
| redis | 222 | redis_acl_access_denied_auth_total, redis_acl_access_denied_channel_total, redis_acl_access_denied_cmd_total, redis_acl_access_denied_key_total, redis_active_defrag_running, redis_allocator_active_bytes, redis_allocator_allocated_bytes, redis_allocator_frag_bytes |
| sonda-http | 18 | probe_dns_lookup_time_seconds, probe_duration_seconds, probe_failed_due_to_regex, probe_http_content_length, probe_http_duration_seconds, probe_http_redirects, probe_http_ssl, probe_http_status_code |
| sonda-redis | 13 | ALERTS, ALERTS_FOR_STATE, probe_dns_lookup_time_seconds, probe_duration_seconds, probe_failed_due_to_regex, probe_ip_addr_hash, probe_ip_protocol, probe_success |
| sonda-tcp | 13 | ALERTS, ALERTS_FOR_STATE, probe_dns_lookup_time_seconds, probe_duration_seconds, probe_failed_due_to_regex, probe_ip_addr_hash, probe_ip_protocol, probe_success |

## Reglas de alerta cargadas

| Alerta | Grupo | Severidad | Estado | Salud |
| :-- | :-- | :-- | :-- | :-- |
| BaseNoDisponible | fixture2030-disponibilidad | critica | inactive | ok |
| SondaExternaFallida | fixture2030-disponibilidad | advertencia | inactive | ok |
| TargetDeMonitoreoCaido | fixture2030-disponibilidad | advertencia | inactive | ok |
| LatenciaAPIp95SobreSLO | fixture2030-rendimiento | advertencia | inactive | ok |
| TasaErrores5xxAlta | fixture2030-rendimiento | critica | inactive | ok |
| CacheComentariosDegradada | fixture2030-rendimiento | advertencia | inactive | ok |
| RedisMemoriaAlta | fixture2030-rendimiento | advertencia | inactive | ok |

## Consultas PromQL documentadas (valor al momento de la verificacion)

- **Q1 Targets UP por job** (1 = UP, 0 = DOWN, ventana instantanea): componente=neo4j,instance=host.docker.internal:7687,job=sonda-tcp: 1; componente=redis,instance=host.docker.internal:6379,job=sonda-redis: 1; componente=prometheus,instance=localhost:9090,job=prometheus: 1; componente=influxdb,instance=http://host.docker.internal:8181/health,job=sonda-http: 1; componente=mongodb,instance=mongodb-exporter:9216,job=mongodb: 1; componente=redis,instance=redis-exporter:9121,job=redis: 1; componente=neo4j,instance=http://host.docker.internal:7474/,job=sonda-http: 1; componente=cassandra,instance=host.docker.internal:9042,job=sonda-tcp: 1
- **Q2 Throughput de la API** (requests/s, ventana 1 min): total: 0
- **Q3 Latencia p95 de la API** (segundos, ventana 1 min): total: nan
- **Q4 Tasa de errores 5xx de la API** (proporcion (0-1), ventana 1 min): total: nan
- **Q5 Latencia p95 por base** (segundos, ventana 1 min): fuente=mongodb: nan; fuente=neo4j: nan; fuente=iris: nan; fuente=redis: nan; fuente=cassandra: nan; fuente=influxdb: nan
- **Q6 Disponibilidad por base vista por la API** (1 = disponible, ventana instantanea): componente=api,fuente=mongodb,instance=host.docker.internal:8000,job=api-fixture: 1; componente=api,fuente=neo4j,instance=host.docker.internal:8000,job=api-fixture: 1; componente=api,fuente=cassandra,instance=host.docker.internal:8000,job=api-fixture: 1; componente=api,fuente=redis,instance=host.docker.internal:8000,job=api-fixture: 1; componente=api,fuente=influxdb,instance=host.docker.internal:8000,job=api-fixture: 1; componente=api,fuente=iris,instance=host.docker.internal:8000,job=api-fixture: 1
- **Q7 Tasa de aciertos de la cache de comentarios** (proporcion (0-1), ventana 1 min): total: nan
- **Q8 Memoria de Redis usada / maxima** (proporcion (0-1), ventana instantanea): componente=redis,instance=redis-exporter:9121,job=redis: 0.0162
- **Q9 Sondas externas que fallan** (1 = OK, 0 = falla, ventana instantanea): componente=neo4j,instance=host.docker.internal:7687,job=sonda-tcp: 1; componente=redis,instance=host.docker.internal:6379,job=sonda-redis: 1; componente=influxdb,instance=http://host.docker.internal:8181/health,job=sonda-http: 1; componente=neo4j,instance=http://host.docker.internal:7474/,job=sonda-http: 1; componente=cassandra,instance=host.docker.internal:9042,job=sonda-tcp: 1; componente=iris,instance=host.docker.internal:1972,job=sonda-tcp: 1; componente=mongodb,instance=host.docker.internal:27017,job=sonda-tcp: 1
- **Q10 Escrituras en Cassandra por partido** (escrituras/s, ventana 1 min): partido=H13-20261126-054628-P1: 0; partido=H13-20261126-054628-P2: 0
