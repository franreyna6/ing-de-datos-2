# Integridad de la corrida `base-20261122-233109`

**Veredicto: OK**

| Control | Valor |
|---|---:|
| escrituras_enviadas | 10322 |
| escrituras_aceptadas_201 | 10322 |
| escrituras_rechazadas | 0 |
| reintentos_enviados | 737 |
| reintentos_aceptados | 737 |
| comentario_ids_unicos_aceptados | 9585 |
| filas_en_cassandra | 10322 |
| comentario_ids_unicos_en_cassandra | 9585 |
| perdidos | 0 |
| alterados | 0 |
| escritos_sin_confirmacion | 0 |
| lecturas_totales | 24469 |
| lecturas_con_respuesta_incoherente | 0 |
| duplicados_por_reintento (ids / filas extra) | 707 / 737 |
| duplicados_inesperados (ids / filas extra) | 0 / 0 |

Rechazos por causa: `{}`

Filas por particion (partido, ventana UTC): `{'P1 23:30': 7164, 'P1 23:35': 132, 'P2 23:30': 1966, 'P2 23:35': 34, 'P3 23:30': 1011, 'P3 23:35': 15}`

Redis: `{"claves_de_cache_que_siguen_vivas": 0, "claves_de_cache_sin_ttl": 0, "evicted_keys_durante_la_prueba": 0.0, "claves_sesion_antes_despues": [0, 0]}`

Conciliacion de tres fuentes: 201 vistos por el cliente = 10322; escrituras contadas por Cassandra (nodetool) = 10322.0; filas leidas con cqlsh = 10322

- Observacion: 707 comentarios quedaron con mas de una fila por reintentos del cliente: la clave de idempotencia (comentarioId) NO evita el duplicado porque creado_en (asignado por la API en cada request) forma parte de la clave primaria. Ver docs/integridad_y_limitaciones.md.
