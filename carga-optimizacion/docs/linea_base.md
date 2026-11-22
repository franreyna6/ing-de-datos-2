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

> **Completar después de correr la línea base**, copiando los valores de `docs/evidencia/<etiqueta-base>/resumen.md`. No escribir valores que no salgan de ese archivo.

| Dato | Valor |
| :--- | :--- |
| Etiqueta de la corrida | *pendiente* |
| Fecha (UTC) | *pendiente* |
| Commit | *pendiente* |
| Cliente de Cassandra de la API (log `modo=`) | *pendiente* |
| Versiones observadas (Cassandra, Redis, Docker) | *pendiente* |
| Máquina (CPU, RAM, sistema operativo) | *pendiente* |
| Escala de usuarios | *pendiente* |
| Motivo de fin | *pendiente* |
| Sostenimiento: ops ok/s, p50, p95 y p99 | *pendiente* |
| Lecturas: p95 en el cliente y en la API | *pendiente* |
| Escrituras: p95 en el cliente y en la API | *pendiente* |
| Tasa de error y tipos | *pendiente* |
| Lecturas que llegaron a Cassandra | *pendiente* |
| CPU de Cassandra y de la API (promedio y máximo) | *pendiente* |
| Integridad (veredicto) | *pendiente* |
| Observaciones de estabilidad | *pendiente* (por ejemplo, si el p95 crece a lo largo del sostenimiento en `serie_por_segundo.csv`) |
