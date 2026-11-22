# Corrida `base-20261122-233109` (base)

- Fecha (UTC): 2026-11-22T23:31:17.814944+00:00 -> 2026-11-22T23:35:08.408029+00:00
- Commit: `af80239` (cambios sin commitear en codigo: False)
- Cache de la API: OFF (verificacion: ['OFF', 'OFF'])
- Cliente Cassandra de la API: driver (indicio)
- Escenario: `pico-post-gol` sha256 `7805deb79b80`; plan sha256 `ac78aea13931`; escala de usuarios x1.0
- Fin: **completa**

## Fases medidas (sin calentamiento)

Latencias en ms medidas en el cliente (generador), solo operaciones exitosas.

| Fase | Ops | Exitosas | Errores | Tasa err. | Ops ok/s | p50 | p95 | p99 | max | Acierto cache |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| calentamiento | 481 | 481 | 0 | 0.0 | 24.1 | 10.46 | 20.17 | 27.95 | 30.57 | None |
| rampa | 4241 | 4241 | 0 | 0.0 | 106.0 | 11.42 | 20.92 | 32.72 | 63.74 | None |
| sostenimiento | 22408 | 22408 | 0 | 0.0 | 186.5 | 12.76 | 23.27 | 48.91 | 186.25 | None |
| pico | 5525 | 5525 | 0 | 0.0 | 276.0 | 15.41 | 29.2 | 61.59 | 85.93 | None |
| recuperacion | 2136 | 2136 | 0 | 0.0 | 71.2 | 11.31 | 20.34 | 29.88 | 46.83 | None |
| **TOTAL MEDIDO** | 34310 | 34310 | 0 | 0.0 | 163.3 | 12.87 | 24.04 | 49.91 | 186.25 | None |

## Por tipo de operacion (fases medidas)

| Tipo | Ops | Tasa err. | Cliente p50 | Cliente p95 | Cliente p99 | API p50 | API p95 | Brecha p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lectura | 24122 | 0.0 | 13.1 | 24.23 | 50.13 | 12.05 | 22.14 | 2.65 |
| escritura | 10188 | 0.0 | 12.36 | 23.56 | 49.4 | 11.28 | 21.23 | 2.8 |

*Brecha = latencia en el cliente - tiempo dentro de la API (red local, cola de conexiones, serializacion HTTP y el propio generador).*

## Control del generador

`{"ops_por_s_observadas_sostenimiento": 186.6, "ops_por_s_esperadas_lazo_cerrado": 187.1}`

## Lo que llego a Cassandra (nodetool, diferencia antes/despues)

`{"lecturas_que_llegaron_a_cassandra": 24469.0, "escrituras_que_llegaron_a_cassandra": 10322.0, "latencia_local_despues": {"latencia_lectura_local_ms": 0.132, "latencia_escritura_local_ms": 0.022}, "percentiles_locales_us": {"50%": {"lectura_us": 124.0, "escritura_us": 20.0}, "95%": {"lectura_us": 179.0, "escritura_us": 35.0}, "99%": {"lectura_us": 215.0, "escritura_us": 60.0}, "Max": {"lectura_us": 152321.0, "escritura_us": 149.0}}}`

## Redis (INFO, antes -> despues)

`{"evicted_keys": 0.0, "keyspace_hits": 0.0, "keyspace_misses": 0.0, "used_memory_antes": "1.41M", "used_memory_despues": "1.43M", "maxmemory_policy": "volatile-lru", "claves_sesion_antes": 0, "claves_sesion_despues": 0}`

## Recursos (promedio / maximo)

| Medida | Promedio | Max | Muestras |
|---|---:|---:|---:|
| api_cpu_pct | 34.2 | 60.8 | 48 |
| api_rss_mib | 121.0 | 126.3 | 48 |
| cassandra_cpu_pct | 42.2 | 107.7 | 48 |
| cassandra_mem_mib | 4775.9 | 4798.5 | 48 |
| generador_cpu_pct | 5.8 | 10.5 | 48 |
| host_cpu_pct | 17.2 | 24.6 | 48 |
| host_mem_pct | 75.7 | 76.9 | 48 |
| redis_cpu_pct | 0.5 | 3.6 | 48 |
| redis_mem_mib | 7.2 | 7.7 | 48 |
