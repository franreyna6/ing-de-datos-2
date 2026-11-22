# Flujo seleccionado y escenario de carga (RF1, RF2)

## 1. Flujo seleccionado: comentarios de un partido en vivo

**Situación del Fixture.** Hay un gol en un partido del Mundial 2030. En los segundos siguientes, miles de hinchas abren el partido en la app para leer qué dice el resto (lectura) y publicar su propio comentario (escritura). Es el escenario "pico después del gol" de la Clase 13.

| Aspecto | Descripción |
| :--- | :--- |
| Consumidor | La app del hincha, a través de la API del Hito 10. En la prueba lo representan los usuarios virtuales del generador. |
| Operación de lectura | `GET /partidos/{codigo}/comentarios?limit=20`: los 20 comentarios más recientes de la ventana de 5 minutos **actual** del partido. |
| Operación de escritura | `POST /partidos/{codigo}/comentarios` con `{usuarioId, contenido, comentarioId}`. |
| Tipo | Combinación de lectura y escritura sobre la misma partición, en tiempo real. |
| Fuente | **Cassandra**, tabla `comentarios_por_partido`, con `PRIMARY KEY ((partido_id, ventana), creado_en, comentario_id)` (Hito 6). Cada request lee o escribe **una** partición; no hay `ALLOW FILTERING`. |
| Fuente adicional (optimizada) | **Redis** como caché de lectura de la ventana actual, con TTL de 2 s (Hito 7). |
| Datos que recibe | El código de partido en la ruta, `limit` en la query y el cuerpo JSON en el POST. |
| Respuesta esperada (GET) | `200` con `{partido, ventana, comentarios[]}`. `partido` tiene que ser el pedido y la lista no puede superar `limit`. |
| Respuesta esperada (POST) | `201` con `{partido, ventana, comentarioId, creadoEn}`. `comentarioId` tiene que ser el enviado. |
| Criterio de éxito | Código HTTP esperado **y** cuerpo coherente. Además, tras la prueba, `validar_integridad.py` comprueba que lo aceptado esté efectivamente en Cassandra. Un `201` no se toma como prueba suficiente. |
| Respuestas degradadas o errores registrados | `503` (dependencia caída), `400`, `500`, timeout del cliente (5 s), error de conexión y `respuesta_inconsistente` (código correcto pero cuerpo incoherente). Cada uno se registra con su tipo en `operaciones.csv.gz`. |
| Volumen y frecuencia proyectados | Durante un partido, hasta millones de lectores simultáneos sobre unos pocos partidos (Clase 13). En el laboratorio se prueba como máximo con 60 usuarios virtuales (ver la sección 2). |

**Por qué este flujo.** Es el patrón de mayor concurrencia del módulo de comentarios y concentra la carga en una **clave caliente**: el partido del gol y su ventana actual. Combina lecturas y escrituras sobre la misma partición. Además, todos los lectores piden exactamente la misma respuesta en la misma ventana de tiempo, y eso abre una oportunidad concreta de optimización. Usa dos módulos del curso (Cassandra y Redis) a través de la API, como pide la consigna.

## 2. Escenario de carga

El escenario está definido en `config/escenario.json`, que es el mismo archivo para las dos corridas.

### Modelo de usuarios

Los usuarios virtuales trabajan en **lazo cerrado**: cada uno toma la siguiente operación del plan, la ejecuta, espera una pausa aleatoria de entre 0,1 y 0,3 s (como un usuario que lee la pantalla) y repite. La tasa de operaciones no está fija: resulta de cuántos usuarios hay activos y de cuánto tarda la API.

Como referencia, sin contar la latencia, cada usuario genera como máximo unas 5 operaciones por segundo (1 / 0,2 s), y 40 usuarios llegan a unas 200 por segundo. El valor efectivamente alcanzado se mide y se compara contra este máximo teórico en el *control del generador*.

### Fases

| Fase | Duración | Usuarios activos | ¿Se mide? | Propósito (Clase 13) |
| :--- | ---: | :--- | :---: | :--- |
| Calentamiento | 20 s | 5 | no | Abrir conexiones, preparar statements y cargar cachés de la JVM y del driver. Se descarta de las métricas, pero sus escrituras sí se validan. |
| Rampa | 40 s | de 5 a 40, en forma lineal | sí | Subida progresiva hacia el pico. |
| Sostenimiento | 120 s | 40 | sí | Observar la estabilidad. Es la fase principal de comparación. |
| Pico | 20 s | 60 | sí | Ráfaga inmediata al gol. |
| Recuperación | 30 s | 15 | sí | Volver a una carga menor y ver si el sistema se normaliza. |

La duración total es de unos **230 s**.

### Proporciones y distribución

- **Lectura / escritura / reintento**: 70 % / 28 % / 2 %.
- **Partidos**: P1 70 % (clave caliente), P2 20 %, P3 10 %.
- **Ventana temporal**: siempre la actual, porque las lecturas no envían `instante` y las escrituras toman la hora de la API. Si la prueba cruza un límite de 5 minutos, la partición caliente cambia, igual que en un partido real.
- **Usuarios**: 5.000 posibles, elegidos de forma uniforme.

### Condición de finalización

La prueba termina por una de cuatro causas:

1. Se completan todas las fases (`motivo_fin: completa`).
2. **Corte seguro**: en los últimos 10 s la tasa de error supera el 30 % o el p95 supera los 5.000 ms.
3. Se agota el plan de operaciones. El plan tiene 120.000 operaciones, que alcanzan para unas 520 operaciones por segundo promedio.
4. El usuario corta con Ctrl+C.

En todos los casos se esperan las requests en vuelo y se guarda lo medido. Una corrida que no termina completa queda marcada como tal, y `comparar_resultados.py` lo advierte.

### Comportamiento ante timeout o error

- El timeout del cliente es de **5 s**, mayor que `DEP_TIMEOUT_S=3` de la API. Así, una base lenta aparece como `503` de la API y no como un timeout del generador.
- El generador **no reintenta automáticamente** los errores, para no inflar ni ocultar la tasa de error. Los únicos reintentos son el 2 % planificado, que siempre se ejecuta y es idéntico en las dos corridas.
- Ante un error de conexión o un timeout, el usuario virtual cierra su conexión, abre una nueva y sigue con la siguiente operación.

### Limpieza o reutilización del ambiente

Cada corrida escribe en partidos propios (`H12-<etiqueta>-P*`), así que el ambiente se puede reutilizar sin borrar nada. La limpieza es opcional y está descrita en el README.

## 3. Qué se compara

La única variable que cambia entre la línea base y la prueba optimizada es `CACHE_COMENTARIOS_TTL_S` (0 → 2). El escenario, el plan, la escala, la máquina, el commit y el cliente de Cassandra se verifican y quedan registrados (ver `comparar_resultados.py`).

Por el modelo de lazo cerrado, si la API responde más rápido, los mismos usuarios en el mismo tiempo ejecutan **más** operaciones. Por eso la cantidad total de operaciones no es idéntica entre corridas, y es esperable. Lo que se mantiene igual es la demanda: los usuarios, las pausas, las fases y la mezcla. Se compara por percentiles, tasa de error y throughput, no por totales (RNF3).
