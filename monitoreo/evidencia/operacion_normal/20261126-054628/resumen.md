# Operacion normal bajo carga 20261126-054628

Generado por `monitoreo/scripts/ejecutar_prueba_controlada.py` (medir_operacion_normal). Valores de Prometheus sobre toda la ventana de carga y del registro del cliente.

- Commit: `85e91ae` · 2026-11-26T05:46:54Z a 2026-11-26T05:49:55Z (181 s)
- Carga: 20 usuarios virtuales, mezcla de las 6 bases (`generar_carga.py`). Corte rapido: CORTOCIRCUITO_S=10.
- Bases disponibles para la API al terminar: 6/6 · targets UP: 13/13 · sondas OK: 7/7

## API (lo que ve Prometheus)

| Requests/s | p50 | p95 | p99 | Errores 5xx | Aciertos de cache |
| --: | --: | --: | --: | --: | --: |
| 91.6 | 4.5 ms | 24.0 ms | 44.4 ms | 0.00 % | 96.4 % |

## Comparacion entre bases (llamadas de la API a cada fuente, RF7)

| Base | Operaciones/s | p50 | p95 | Fallas/s |
| :-- | --: | --: | --: | --: |
| cassandra | 15.5 | 16.8 ms | 24.3 ms | 0.00 |
| influxdb | 7.1 | 20.3 ms | 45.7 ms | 0.00 |
| iris | 6.5 | 2.8 ms | 5.8 ms | 0.00 |
| mongodb | 13.9 | 1.7 ms | 4.7 ms | 0.00 |
| neo4j | 9.0 | 4.2 ms | 9.4 ms | 0.00 |
| redis | 42.2 | 1.3 ms | 2.5 ms | 0.00 |

## Cliente de carga

- 16607 requests (91.7/s); p50 5.53 ms, p95 24.23 ms, p99 37.58 ms; 5xx: 0; errores de conexion: 0; 4xx: 847.

| Operacion | Requests | p95 cliente | Codigos HTTP |
| :-- | --: | --: | :-- |
| detalle | 1176 | 10.19 ms | {200: 1176} |
| equipo | 1704 | 9.33 ms | {200: 1704} |
| escribir_comentario | 2570 | 22.56 ms | {201: 2570} |
| estadisticas | 1276 | 40.31 ms | {200: 1276} |
| eventos | 1643 | 11.43 ms | {200: 1643} |
| jugadores | 819 | 9.4 ms | {200: 819} |
| leer_comentarios | 6572 | 12.2 ms | {200: 6572} |
| sesion | 847 | 7.32 ms | {404: 847} |

Capturas:

- `../../dashboards/operacion_20261126-054628_tablero_completo.png`
- `../../dashboards/operacion_20261126-054628_salud_infraestructura.png`
- `../../dashboards/operacion_20261126-054628_salud_vista_api.png`
- `../../dashboards/operacion_20261126-054628_throughput.png`
- `../../dashboards/operacion_20261126-054628_latencia_api.png`
- `../../dashboards/operacion_20261126-054628_errores.png`
- `../../dashboards/operacion_20261126-054628_latencia_por_base.png`
- `../../dashboards/operacion_20261126-054628_operaciones_por_base.png`
- `../../dashboards/operacion_20261126-054628_cache.png`
- `../../dashboards/operacion_20261126-054628_memoria_redis.png`
- `../../dashboards/operacion_20261126-054628_escrituras_cassandra.png`
- `../../dashboards/operacion_20261126-054628_corte_rapido.png`
