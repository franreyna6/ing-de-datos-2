# Hipótesis de cuello de botella y optimización (RF7, RF8, RF9, RF10, RF11)

## 1. Hipótesis principal (formulada antes del cambio)

**H1. La lectura en vivo repite el mismo trabajo cientos de veces por segundo.**

Después del gol, el 70 % de las operaciones son lecturas, y el 70 % de ellas apuntan al mismo partido. Todas piden lo mismo: los 20 comentarios más recientes de la misma partición (`partido`, `ventana` actual).

En la versión del Hito 10, **cada** una de esas lecturas recorre el camino completo: un hilo de la API, una consulta a Cassandra por el driver, la lectura de la partición y la serialización de la respuesta. El resultado es casi idéntico entre una lectura y la siguiente, porque solo cambia cuando entra un comentario nuevo.

Se espera entonces que, con más usuarios, las lecturas compitan por los hilos de la API y por Cassandra, y que eso se vea en el p95 y el p99 de las lecturas y en la CPU de Cassandra. Las escrituras también se verían afectadas, porque comparten la misma API y la misma base.

**Prueba propuesta para relacionar la hipótesis con la evidencia.**

En la línea base, H1 se sostiene si se observa lo siguiente:

- Las **lecturas que llegaron a Cassandra** (`nodetool`) son aproximadamente iguales a las lecturas HTTP. Es decir, cada GET va a la base.
- El p95 de las lecturas crece al pasar de la rampa al sostenimiento y al pico (`resumen.md` por fase y `serie_por_segundo.csv`).
- La CPU de Cassandra o de la API sube con la carga (`recursos.csv`).

Después del cambio, si H1 es correcta, deberían bajar las lecturas que llegan a Cassandra (aproximadamente en la proporción de aciertos de caché) y el p95 de las lecturas, sin que aumenten los errores ni se pierdan datos.

Si en cambio el p95 de la API es mucho menor que el p95 del cliente (brecha grande), o si el control del generador muestra que no se alcanzó la carga esperada, la hipótesis no se puede evaluar: el límite estaría en el generador o en la red local, no en la API ni en la base.

## 2. Hipótesis alternativas que se descartan o controlan

| Hipótesis | Cómo se controla |
| :--- | :--- |
| **H0. El cliente de Cassandra.** Si la API corre con Python 3.12, el driver nativo no carga y el adaptador usa `cqlsh` mediante `docker exec`, que lanza un proceso por cada request. Ese sería el cuello de botella dominante, y una caché lo ocultaría sin resolverlo. | Antes de interpretar, se verifica en el log de la API qué modo usó (`modo=driver` o `modo=cqlsh`), y el mismo modo tiene que repetirse en las dos corridas. **Si fuera `cqlsh`**, se documenta como el cuello de botella principal y la primera optimización pasa a ser correr la API con Python 3.11 para usar el driver nativo, que es una alternativa ya documentada en el Hito 10. |
| **H2. El generador.** El cliente no produce suficientes solicitudes y se atribuye el límite a la API (Clase 13). | Control del generador (operaciones por segundo observadas contra esperadas) y CPU del generador. |
| **H3. Los logs.** La API escribe una o dos líneas por request, y en la consola eso puede frenarla. | El log va a un archivo en las dos corridas, en las mismas condiciones. No se evalúa como optimización. |
| **H4. Los hilos de la API.** Las rutas son sincrónicas, y FastAPI las ejecuta en un pool de hilos con un tope por defecto. Con más usuarios que hilos libres, las requests esperan en cola. | Se refleja en la brecha y en la latencia de la API. No se modifica en este hito, para cambiar una sola cosa por vez. |

## 3. Optimización aplicada: caché de lectura con TTL corto en Redis

| Campo | Registro |
| :--- | :--- |
| Problema que se intenta resolver | H1: lecturas idénticas y repetidas sobre la partición caliente, que van todas a Cassandra. |
| Cambio implementado | Patrón *cache-aside* (Hito 7) sobre la lectura de la ventana **actual**. La API busca primero en Redis la clave `cache:comentarios:{partido}:{ventana}:{limit}`. Si la encuentra (**HIT**), responde sin ir a Cassandra. Si no (**MISS**), lee Cassandra y guarda la respuesta con `SET ... EX 2`, que siempre tiene TTL. Las lecturas de una ventana histórica (con `instante`) no se cachean. |
| Activación | Variable `CACHE_COMENTARIOS_TTL_S`: `0` es apagada (línea base, comportamiento del Hito 10) y `2` es la versión optimizada. No se cambia otra cosa. |
| Archivos afectados | `api/app/core/config.py` (variable), `api/app/adapters/redis_adapter.py` (`cache_leer` y `cache_guardar`), `api/app/services/servicios.py` (`comentarios_de_partido_con_cache`), `api/app/routes/partidos.py` (header `X-Cache`) y `api/app/main.py` (header `X-Duracion-ms`, solo para medir). |
| Si Redis no responde | Se lee Cassandra. La caché es opcional, así que una falla de Redis no rompe la lectura de comentarios, solo la hace más lenta. Es distinto de las sesiones del Hito 7, donde Redis es la fuente de verdad y una caída es un `503`. |
| Por qué TTL de 2 s y sin invalidación en cada POST | Con 28 % de escrituras concentradas en P1, invalidar la caché en cada POST la vaciaría varias veces por segundo y casi no habría aciertos. Para un feed de comentarios en vivo, mostrar los comentarios con hasta 2 s de atraso es aceptable para el usuario. Es un trade-off explícito (ver la sección 4). |
| Prueba ejecutada después | `ejecutar_prueba_optimizada.py`: el mismo escenario, el mismo plan y la misma escala, verificados por `comparar_resultados.py`. |
| Resultado medido | *Pendiente*: completar con `docs/evidencia/comparacion.md` después de las corridas. |
| Decisión final del equipo | *Pendiente*: se decide con la evidencia. |

## 4. Costos y trade-offs (RF11)

| Costo o riesgo | Detalle | Cómo se observa |
| :--- | :--- | :--- |
| **Frescura** | Un comentario recién publicado puede tardar hasta 2 s (el TTL) en aparecer para los demás lectores. El autor recibe su `201` igual, pero no lo ve en la lista hasta que vence la entrada. Es un límite de diseño, no una medición: no se midió la frescura percibida por el usuario. | Diseño: TTL = 2 s. |
| **Estampida al vencer el TTL** | Cuando una entrada vence, todas las lecturas concurrentes de ese partido son MISS al mismo tiempo y van juntas a Cassandra hasta que alguna vuelve a guardar la página. Se espera que eso se vea como picos periódicos de latencia, que afectan sobre todo al p99. | `serie_por_segundo.csv` y gráfico de p95 en el tiempo. Comparar el p99 con el p95. |
| **Memoria y expulsión en Redis** (corrección del Hito 7) | Las claves de caché llevan TTL, igual que las sesiones. Con `maxmemory 100mb` y `volatile-lru`, si la caché llenara la memoria, Redis podría expulsar sesiones vigentes para hacer lugar a páginas de comentarios. En esta prueba hay pocas claves (3 partidos × ventanas × 1 `limit`), así que el riesgo es bajo. Pero crece con la cantidad de partidos, ventanas y valores de `limit`. Mitigación propuesta: una instancia de Redis separada para la caché, o incluir el riesgo en el cálculo de memoria del Hito 7. | `evicted_keys` y sesiones antes y después (`metadata.json` e `integridad.md`). |
| **Complejidad** | Hay un camino más en la lectura (HIT, MISS, falla de Redis) y una dependencia más en el flujo. | Código encapsulado en una función y una variable de entorno. |
| **Duplicación** | La misma página existe en Cassandra y en Redis durante 2 s. No es fuente de verdad: si se pierde, se reconstruye. | No hay escrituras en la caché fuera del MISS. |
| **Alcance** | Solo mejora las lecturas en vivo y repetidas. No acelera las escrituras ni las lecturas históricas, y no resuelve una partición demasiado grande. | Comparación por tipo de operación. |

## 5. Resultado y decisión

> Completar a partir de `docs/evidencia/comparacion.md`, citando solo valores medidos: variación de p50, p95 y p99 por tipo, throughput, tasa de error, lecturas que llegaron a Cassandra, tasa de aciertos, CPU, `evicted_keys` y veredicto de integridad de las dos corridas. Indicar si hubo regresiones, por ejemplo en el p99 por la estampida o en las escrituras.
