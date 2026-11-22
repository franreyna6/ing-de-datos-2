# Línea base (RF4, RF5, RF6)

La línea base es la corrida del escenario con la API **tal como quedó en el Hito 10**, es decir, con `CACHE_COMENTARIOS_TTL_S=0`. En ese modo, cada lectura va a Cassandra exactamente como antes. El script se niega a correr si la API no responde `X-Cache: OFF`.

## Dónde está la evidencia

Toda la evidencia queda en `docs/evidencia/<etiqueta-base>/`:

| Archivo | Contenido |
| :--- | :--- |
| `metadata.json` | Commit, fecha, versiones observadas, entorno, escenario y hashes, contadores antes y después, y recursos. |
| `resumen.md` y `resumen.json` | Métricas por fase y por tipo de operación, en formato legible y en JSON. |
| `operaciones.csv.gz` | **Una fila por operación ejecutada**: fase, tipo, partido, segundo, código HTTP, éxito, error, latencia en el cliente, latencia en la API, estado de caché, cantidad de comentarios, `comentarioId` y ventana. |
| `serie_por_segundo.csv` | Operaciones, errores, p50, p95 y p99 de cada segundo de la prueba. |
| `recursos.csv` | Muestras cada 3 s de CPU y memoria de Cassandra, Redis, la API, la máquina y el generador. |
| `integridad.md` y `integridad.json` | Resultado de `validar_integridad.py`. |

## Qué se mide y cómo (RNF5)

| Métrica | Método | Unidad |
| :--- | :--- | :--- |
| Latencia en el cliente | `time.perf_counter()` alrededor de la request HTTP completa, en el generador. | ms |
| Latencia dentro de la API | Header `X-Duracion-ms`, medido por el middleware de la API desde que entra la request hasta que sale la respuesta. | ms |
| Percentiles | p50, p90, p95, p99, mínimo, máximo y promedio, por rango más cercano y solo sobre operaciones exitosas. Los errores se cuentan aparte. | ms |
| Throughput | Operaciones exitosas divididas por los segundos reales de la fase. | ops/s |
| Errores | Cantidad, tasa y desglose por tipo (`http_503`, `timeout_cliente`, `respuesta_inconsistente`, etc.). | cantidad y proporción |
| Concurrencia | Usuarios virtuales activos por fase (configurada) y throughput resultante (medido). | usuarios |
| Lecturas y escrituras que llegaron a Cassandra | Diferencia de `nodetool tablestats` (`Local read/write count`) entre antes y después. Incluye el calentamiento y las 2 lecturas de verificación. | cantidad |
| Latencia local de Cassandra | `nodetool tablehistograms`: percentiles del tiempo que la base tarda en resolver la operación, sin red ni API. | µs |
| Redis | `INFO`: `evicted_keys`, `keyspace_hits` y `keyspace_misses` (diferencias), y `used_memory` antes y después. | cantidad y bytes |
| CPU y memoria de los contenedores | `docker stats --no-stream` cada 3 s. | % de un núcleo y MiB |
| CPU y memoria de la API y la máquina | `psutil` cada 3 s (opcional). | % y MiB |
| CPU del generador | Tiempo de CPU del propio proceso. | % de un núcleo |

## Separación de capas (RF6)

| Capa | Fuente de la medición | Qué permite concluir |
| :--- | :--- | :--- |
| Generador | Latencia en el cliente, CPU del generador y *control del generador*, que compara las operaciones por segundo observadas con las esperadas en lazo cerrado. | Si el generador produce la carga que dice producir. Si observado y esperado no se parecen, o si la CPU del generador está saturada, no se puede culpar a la API. |
| Red local y cola HTTP | **Brecha** = latencia en el cliente − latencia en la API. | El tiempo que la request pasa fuera de la lógica de la API: conexión, cola de uvicorn y serialización HTTP. |
| API | `X-Duracion-ms`, CPU y RSS del proceso de uvicorn. | El tiempo total de la API, que incluye esperar a Cassandra o Redis. |
| Producto NoSQL | `nodetool` (conteos y percentiles locales), `INFO` de Redis y `docker stats`. | Cuánto del tiempo de la API es tiempo de la base, y cuántas operaciones le llegaron. |
| Sistema operativo | `psutil` (CPU y memoria de la máquina). | Si la notebook entera estaba saturada. |

## Registro de la línea base

Valores copiados de `docs/evidencia/base-20261122-233109/resumen.md`, `metadata.json` e `integridad.md`. Latencias en ms, medidas en el cliente, solo operaciones exitosas.

| Dato | Valor |
| :--- | :--- |
| Etiqueta de la corrida | `base-20261122-233109` |
| Fecha (UTC) | 2026-11-22 23:31:17 → 23:35:08 (230,5 s) |
| Commit | `af80239`, sin cambios sin commitear en el código |
| Cliente de Cassandra de la API | Driver nativo: el log de la API muestra `modo=driver` |
| Versiones observadas | Cassandra 5.0.9, Redis 8.10.3, Docker 29.8.0, Python 3.11.9 |
| Máquina | Windows, compilación 10.0.26200, Intel de 12 núcleos lógicos, 15,9 GiB de RAM |
| Escala de usuarios | ×1,0 (hasta 60 usuarios virtuales) |
| Motivo de fin | Completa |
| Operaciones medidas | 34.310, todas exitosas (34.791 consumidas del plan, incluido el calentamiento) |
| Sostenimiento (40 usuarios) | 186,5 ops ok/s; p50 12,76, p95 23,27, p99 48,91, máximo 186,25 |
| Pico (60 usuarios) | 276,0 ops ok/s; p50 15,41, p95 29,20, p99 61,59 |
| Lecturas | p95 24,23 en el cliente y 22,14 dentro de la API |
| Escrituras | p95 23,56 en el cliente y 21,23 dentro de la API |
| Tasa de error | 0 % (ningún error de ningún tipo) |
| Lecturas que llegaron a Cassandra (`nodetool`) | 24.469, igual a las 24.469 lecturas HTTP (incluye calentamiento y verificación) |
| Latencia local de lectura de Cassandra (`tablehistograms`) | p50 124 µs, p95 179 µs, p99 215 µs |
| CPU de Cassandra | 42,2 % de promedio y 107,7 % de máximo (% de un núcleo) |
| CPU de la API | 34,2 % de promedio y 60,8 % de máximo |
| CPU del generador | 5,8 % de promedio; operaciones observadas 186,6/s contra 187,1/s esperadas en lazo cerrado |
| Integridad | **OK**: 10.322 aceptadas, 10.322 filas en Cassandra, 0 perdidas, 0 alteradas, 0 duplicados inesperados |

### Lectura de la línea base

- **El generador no fue el límite.** Produjo la carga esperada (186,6 contra 187,1 ops/s en el sostenimiento) usando menos del 11 % de un núcleo.
- **La red local y la cola HTTP aportan poco.** La brecha entre cliente y API es de 2,65 ms en el p95 de lecturas. Casi todo el tiempo transcurre dentro de la API.
- **Cada lectura HTTP fue a Cassandra**, como prevé la hipótesis H1: 24.469 lecturas en la base para 24.469 lecturas HTTP.
- **El tiempo no está en el motor de Cassandra.** Cassandra resuelve cada lectura localmente en unos 0,12 ms (p50), pero la API tarda unos 12 ms (p50). La mayor parte del tiempo está en el viaje de ida y vuelta desde la API hasta la base: el driver, la red de Docker Desktop entre Windows y el contenedor, y la espera por un hilo de la API. Esta prueba no separó esas partes entre sí.
- **Estabilidad.** No hubo errores. El p95 promedio por segundo subió de 26,9 ms (primeros 40 s del sostenimiento) a 29,7 ms (últimos 40 s), y hubo picos aislados de hasta 150 ms en un segundo (`serie_por_segundo.csv`). El p99 crece con la carga: 32,7 en la rampa, 48,9 en el sostenimiento y 61,6 en el pico.
