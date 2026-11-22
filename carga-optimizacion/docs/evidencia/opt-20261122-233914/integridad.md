# Integridad de la corrida `opt-20261122-233914`

**Veredicto: OK**

| Control | Valor |
|---|---:|
| escrituras_enviadas | 10762 |
| escrituras_aceptadas_201 | 10762 |
| escrituras_rechazadas | 0 |
| reintentos_enviados | 765 |
| reintentos_aceptados | 765 |
| comentario_ids_unicos_aceptados | 9997 |
| filas_en_cassandra | 10762 |
| comentario_ids_unicos_en_cassandra | 9997 |
| perdidos | 0 |
| alterados | 0 |
| escritos_sin_confirmacion | 0 |
| lecturas_totales | 25428 |
| lecturas_con_respuesta_incoherente | 0 |
| duplicados_por_reintento (ids / filas extra) | 735 / 765 |
| duplicados_inesperados (ids / filas extra) | 0 / 0 |

Rechazos por causa: `{}`

Filas por particion (partido, ventana UTC): `{'P1 23:35': 290, 'P1 23:40': 7319, 'P2 23:35': 68, 'P2 23:40': 2032, 'P3 23:35': 22, 'P3 23:40': 1031}`

Redis: `{"claves_de_cache_que_siguen_vivas": 0, "claves_de_cache_sin_ttl": 0, "evicted_keys_durante_la_prueba": 0.0, "claves_sesion_antes_despues": [0, 0]}`

Conciliacion de tres fuentes: 201 vistos por el cliente = 10762; escrituras contadas por Cassandra (nodetool) = 10762.0; filas leidas con cqlsh = 10762

- Observacion: 735 comentarios quedaron con mas de una fila por reintentos del cliente: la clave de idempotencia (comentarioId) NO evita el duplicado porque creado_en (asignado por la API en cada request) forma parte de la clave primaria. Ver docs/integridad_y_limitaciones.md.
