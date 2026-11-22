# Corrida `opt-20261122-233914` (opt)

- Fecha (UTC): 2026-11-22T23:39:25.609514+00:00 -> 2026-11-22T23:43:16.217889+00:00
- Commit: `af80239` (cambios sin commitear en codigo: False)
- Cache de la API: ON (verificacion: ['MISS', 'HIT'])
- Cliente Cassandra de la API: driver (indicio)
- Escenario: `pico-post-gol` sha256 `7805deb79b80`; plan sha256 `ac78aea13931`; escala de usuarios x1.0
- Fin: **completa**

## Fases medidas (sin calentamiento)

Latencias en ms medidas en el cliente (generador), solo operaciones exitosas.

| Fase | Ops | Exitosas | Errores | Tasa err. | Ops ok/s | p50 | p95 | p99 | max | Acierto cache |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| calentamiento | 487 | 487 | 0 | 0.0 | 24.4 | 5.51 | 21.22 | 32.12 | 37.74 | 0.9148 |
| rampa | 4369 | 4369 | 0 | 0.0 | 109.1 | 2.77 | 17.68 | 25.53 | 46.96 | 0.9758 |
| sostenimiento | 23300 | 23300 | 0 | 0.0 | 193.9 | 2.83 | 17.05 | 24.98 | 48.16 | 0.9841 |
| pico | 5831 | 5831 | 0 | 0.0 | 291.2 | 3.23 | 17.52 | 25.95 | 48.98 | 0.99 |
| recuperacion | 2203 | 2203 | 0 | 0.0 | 73.4 | 2.85 | 17.51 | 22.4 | 47.41 | 0.9672 |
| **TOTAL MEDIDO** | 35703 | 35703 | 0 | 0.0 | 169.8 | 2.89 | 17.23 | 24.89 | 48.98 | 0.983 |

## Por tipo de operacion (fases medidas)

| Tipo | Ops | Tasa err. | Cliente p50 | Cliente p95 | Cliente p99 | API p50 | API p95 | Brecha p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lectura | 25076 | 0.0 | 2.29 | 7.05 | 20.83 | 1.63 | 5.44 | 1.39 |
| escritura | 10627 | 0.0 | 11.04 | 19.91 | 31.53 | 10.25 | 18.68 | 1.57 |

*Brecha = latencia en el cliente - tiempo dentro de la API (red local, cola de conexiones, serializacion HTTP y el propio generador).*

## Control del generador

`{"ops_por_s_observadas_sostenimiento": 194.0, "ops_por_s_esperadas_lazo_cerrado": 194.6}`

## Lo que llego a Cassandra (nodetool, diferencia antes/despues)

`{"lecturas_que_llegaron_a_cassandra": 456.0, "escrituras_que_llegaron_a_cassandra": 10762.0, "latencia_local_despues": {"latencia_lectura_local_ms": 0.127, "latencia_escritura_local_ms": 0.02}, "percentiles_locales_us": {"50%": {"lectura_us": 124.0, "escritura_us": 20.0}, "95%": {"lectura_us": 179.0, "escritura_us": 35.0}, "99%": {"lectura_us": 372.0, "escritura_us": 60.0}, "Max": {"lectura_us": 535.0, "escritura_us": 215.0}}}`

## Redis (INFO, antes -> despues)

`{"evicted_keys": 0.0, "keyspace_hits": 24972.0, "keyspace_misses": 456.0, "used_memory_antes": "1.48M", "used_memory_despues": "1.51M", "maxmemory_policy": "volatile-lru", "claves_sesion_antes": 0, "claves_sesion_despues": 0}`

## Recursos (promedio / maximo)

| Medida | Promedio | Max | Muestras |
|---|---:|---:|---:|
| api_cpu_pct | 28.4 | 49.4 | 49 |
| api_rss_mib | 115.3 | 118.0 | 49 |
| cassandra_cpu_pct | 22.8 | 181.8 | 49 |
| cassandra_mem_mib | 4773.7 | 4799.5 | 49 |
| generador_cpu_pct | 5.8 | 9.6 | 49 |
| host_cpu_pct | 11.0 | 18.2 | 49 |
| host_mem_pct | 75.2 | 76.2 | 49 |
| redis_cpu_pct | 1.3 | 4.3 | 49 |
| redis_mem_mib | 7.8 | 8.6 | 49 |
