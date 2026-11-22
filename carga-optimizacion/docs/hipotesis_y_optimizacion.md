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
| Resultado medido | Lecturas: p95 de 24,23 a 7,05 ms (−70,9 %). Lecturas que llegaron a Cassandra: de 24.469 a 456 (−98,1 %), con 98,3 % de aciertos. Sin errores ni pérdida de datos. Detalle en la sección 5. |
| Decisión final del equipo | **Se adopta** la caché con TTL de 2 s para la lectura en vivo, con el atraso de hasta 2 s declarado como parte del contrato del feed. Antes de llevarla a producción se propone separar la caché de las sesiones (sección 4). |

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

Corridas comparadas: `base-20261122-233109` (sin caché) y `opt-20261122-233914` (con caché). Las dos usan el mismo commit (`af80239`), el mismo escenario y plan (hashes `7805deb7` y `ac78aea1`), la misma escala, la misma máquina y el driver nativo (`modo=driver` en el log de cada corrida). `comparar_resultados.py` no encontró diferencias de condiciones. La tabla completa está en `docs/evidencia/comparacion.md`.

### Valores medidos

Latencias en ms, en el cliente, sobre las fases medidas.

| Métrica | Línea base | Optimizada | Variación |
| :--- | ---: | ---: | ---: |
| Lecturas: p50 / p95 / p99 | 13,10 / 24,23 / 50,13 | 2,29 / 7,05 / 20,83 | −82,5 % / −70,9 % / −58,4 % |
| Lecturas: p95 dentro de la API | 22,14 | 5,44 | −75,4 % |
| Escrituras: p50 / p95 / p99 | 12,36 / 23,56 / 49,40 | 11,04 / 19,91 / 31,53 | −10,7 % / −15,5 % / −36,2 % |
| Total: p50 / p95 / p99 | 12,87 / 24,04 / 49,91 | 2,89 / 17,23 / 24,89 | −77,5 % / −28,3 % / −50,1 % |
| Total: latencia máxima | 186,25 | 48,98 | −73,7 % |
| Pico (60 usuarios): p95 / p99 | 29,20 / 61,59 | 17,52 / 25,95 | −40,0 % / −57,9 % |
| Throughput medido (ops ok/s) | 163,3 | 169,8 | +4,0 % |
| Tasa de error | 0 % | 0 % | — |
| Aciertos de caché en lecturas | — | 98,3 % (99,0 % en el pico) | — |
| Lecturas que llegaron a Cassandra (`nodetool`) | 24.469 | 456 | −98,1 % |
| Escrituras que llegaron a Cassandra (`nodetool`) | 10.322 | 10.762 | +4,3 % (más operaciones en el mismo tiempo) |
| CPU de Cassandra: promedio / máximo | 42,2 % / 107,7 % | 22,8 % / 181,8 % | −46,0 % / ver nota |
| CPU de la API: promedio | 34,2 % | 28,4 % | −17,0 % |
| CPU de la máquina: promedio | 17,2 % | 11,0 % | −36,0 % |
| Memoria de Redis: después de la prueba | 1,43 MB | 1,51 MB | +0,08 MB |
| `evicted_keys` en Redis | 0 | 0 | — |
| Integridad | OK | OK | — |

### Interpretación

- **La hipótesis H1 se confirma.** Con la caché, 98 de cada 100 lecturas se resolvieron en Redis: las lecturas que llegaron a Cassandra bajaron de 24.469 a 456. En la misma proporción bajó el tiempo de las lecturas dentro de la API (p95 de 22,14 a 5,44 ms). Si cada partido tuviera un solo MISS cada 2 s, en unos 230 s y con 3 partidos habría unas 345 lecturas a Cassandra. Se midieron 456. La diferencia, de alrededor de 110, corresponde a MISS simultáneos: varias lecturas encuentran la entrada vencida al mismo tiempo y van juntas a Cassandra antes de que alguna la vuelva a guardar. Es una estampida leve (ver más abajo).
- **También mejoraron las escrituras, aunque la caché no las toca.** El p99 de las escrituras bajó de 49,40 a 31,53 ms. Es un efecto indirecto: al ir muchas menos lecturas a Cassandra, las escrituras compiten menos por los hilos de la API, por la conexión del driver y por la CPU de Cassandra, cuyo promedio bajó a la mitad. El p50 de las escrituras casi no cambió (−10,7 %), porque cada escritura sigue yendo a Cassandra.
- **El p95 total mejora menos que el de las lecturas** (−28,3 % contra −70,9 %). Con la caché, las escrituras, que siguen tardando unos 11 a 20 ms, pasan a ser las operaciones más lentas y son las que definen el percentil 95 total.
- **La latencia se volvió más estable.** El máximo bajó de 186 a 49 ms. En el gráfico `comparacion_p95_en_el_tiempo.png`, la línea base muestra picos de hasta 150 ms en un segundo, mientras que la optimizada se mantiene entre 15 y 35 ms durante toda la prueba.
- **El throughput solo sube un 4 %, y es esperable.** Los usuarios trabajan en lazo cerrado con una pausa de entre 0,1 y 0,3 s, así que la latencia (unos pocos ms) es una parte chica del ciclo de cada usuario. Bajar la latencia agrega pocas operaciones por segundo. Lo que mejora es la experiencia de cada request, no la capacidad máxima, que esta prueba no buscó (no es una prueba de estrés).
- **La estampida al vencer el TTL existe, pero con esta carga es leve.** Se ve en los alrededor de 110 MISS extra del punto anterior. No se nota en la latencia: el p95 por segundo no muestra picos periódicos cada 2 s y el p99 de las lecturas bajó un 58 %. Con un MISS que tarda unos 12 ms, la ventana en la que varias lecturas encuentran la entrada vencida es corta. Con miles de lectores simultáneos esa ventana tendría muchas más lecturas, y no se puede afirmar que siga siendo leve. Una mitigación posible, no implementada, es que solo una lectura reconstruya la entrada mientras las demás devuelven la versión anterior.
- **Nota sobre el máximo de CPU de Cassandra (181,8 %).** Corresponde a una única muestra, la del segundo 230 de la prueba optimizada, que coincide con el final de la carga. Es probable que lo cause el arranque de `nodetool` (una JVM que corre dentro del contenedor) para tomar los contadores posteriores, y no la carga de la prueba. No se verificó por separado. El resto de las muestras de esa corrida no supera el 70 %.

### Costos observados

- **Memoria de Redis:** subió unos 0,08 MB y no hubo expulsiones. Con 3 partidos el costo es despreciable.
- **Frescura:** hasta 2 s de atraso por diseño. No se midió.
- **Riesgo para las sesiones (corrección del Hito 7):** no se pudo observar, porque Redis no tenía sesiones durante la prueba (0 antes y 0 después). La ausencia de expulsiones no demuestra que las sesiones estén protegidas: solo muestra que, con este volumen, la caché no presionó la memoria. Por eso se mantiene la propuesta de usar una instancia de Redis separada para la caché.

### Regresiones

No hubo regresiones en la latencia, los errores ni la integridad. El único valor que empeoró es el máximo de CPU de Cassandra, explicado en la nota anterior.
