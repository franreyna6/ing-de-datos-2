# Integridad y limitaciones (RF15, RNF4, RNF6, RNF14)

## 1. Qué se valida y cómo

`scripts/validar_integridad.py <etiqueta>` se corre después de cada carga. Compara tres fuentes independientes:

1. **Lo que el cliente envió y vio**: `operaciones.csv.gz`.
2. **Lo que quedó en Cassandra**, leído con `cqlsh` partición por partición. Se leen todas las particiones (`partido`, `ventana`) que la corrida pudo tocar entre su inicio y su fin.
3. **Lo que la propia Cassandra contó**: la diferencia de `nodetool` en las escrituras locales.

| Control | Qué detecta |
| :--- | :--- |
| Generadas, aceptadas (`201`) y rechazadas, con causa | Escrituras que la API no aceptó y por qué. |
| Cada `comentarioId` aceptado existe en Cassandra | Comentarios **perdidos**: la API respondió `201` pero el dato no está. |
| Usuario y contenido guardados coinciden con los enviados | Comentarios **alterados** o mezclados. El sufijo `#i` hace único cada contenido. |
| Filas con el mismo `comentario_id` | **Duplicados**, separados en los explicados por un reintento del plan y los inesperados. |
| Filas en la base que el cliente no vio confirmadas | Escrituras que se guardaron aunque el cliente recibió un timeout o un error de conexión. El cliente las vería como fallidas. |
| Conteo por partición | La distribución real por partido y ventana. |
| Conciliación de tres fuentes | `201` vistos por el cliente, escrituras contadas por `nodetool` y filas leídas con `cqlsh`. |
| Lecturas coherentes | Cada `200` de lectura trae el partido pedido y no más de `limit` comentarios. Si no, se registra `respuesta_inconsistente`. |
| Claves de caché con TTL | Ninguna clave de caché de la corrida puede quedar sin vencimiento. |
| Expulsiones en Redis | `evicted_keys` durante la prueba y cantidad de sesiones antes y después (relacionado con la corrección del Hito 7). |

El veredicto es **OK** si no hay perdidos, alterados, duplicados inesperados, lecturas incoherentes ni claves sin TTL.

## 2. Hallazgo de diseño: los reintentos duplican comentarios

El Hito 10 documentó que reenviar el mismo `comentarioId` "reescribe la misma fila". Este hito lo pone a prueba: el plan incluye un 2 % de reintentos que reenvían exactamente el mismo comentario.

**Análisis del modelo.** La clave primaria de la tabla es `((partido_id, ventana), creado_en, comentario_id)`, y la API asigna `creado_en` con la hora de **cada** request. Un reintento tiene entonces otro `creado_en`, es otra clave primaria y genera **otra fila**. La clave de idempotencia no evita el duplicado. Además, si el reintento cae en otra ventana de 5 minutos, ni siquiera queda en la misma partición.

**Cómo se ve en la evidencia.** `validar_integridad.py` cuenta los `comentario_id` que tienen más de una fila, y comprueba que cada caso esté explicado por un reintento que el cliente efectivamente envió. Si aparece un duplicado que ningún reintento explica, se informa como duplicado inesperado y el veredicto pasa a "CON PROBLEMAS".

**Por qué no se corrige en este hito.** Corregirlo requiere cambiar el modelo de Cassandra del Hito 6. Por ejemplo, que el cliente envíe el instante de creación y la API lo use como `creado_en`, o que el orden se base en un identificador que ya contenga el tiempo. Eso modifica la clave de una tabla con datos cargados y excede el objetivo de este hito, que es medir y optimizar un flujo, no rediseñar el modelo.

**Cómo se mitiga hoy.** El Data Mart deduplica por `comentario_id` al cargar (ver `integracion_data_mart.md`), así que los conteos analíticos no se inflan.

**Cómo resuelve esto la alternativa relacional.** Con `comentario_id` como clave primaria, el segundo `INSERT` falla por clave duplicada, y la idempotencia sale naturalmente del modelo (ver `comparacion_relacional.md`).

**Resultado medido**: *pendiente*. Completar con la cantidad de reintentos enviados y de duplicados observados en cada corrida, según `integridad.md`.

## 3. Escalabilidad: volumen probado y capacidad proyectada (RNF6, corrección del Hito 8)

| Dimensión | Probado en el laboratorio (medido) | Proyectado para el Fixture 2030 (no medido) |
| :--- | :--- | :--- |
| Usuarios concurrentes | Hasta 60 usuarios virtuales en una notebook. | Entre 2 y 3 millones de usuarios simultáneos en el escenario (Clase 13). |
| Comentarios | Los escritos por cada corrida (ver `integridad.md`), sobre una tabla que ya tiene más de 1.000.000 de comentarios del Hito 6. | Más de 1.000.000 de comentarios potenciales por torneo. |
| Nodos | 1 nodo de Cassandra y 1 de Redis, sin réplicas. | Un clúster con réplicas, según la arquitectura del Hito 3. |
| Red | Localhost: la API, las bases y el generador en la misma máquina. | Usuarios en varias regiones, con latencia de red real. |

**Qué se puede concluir.** Bajo este escenario, este volumen y esta máquina, se puede decir si la caché reduce la latencia y la carga sobre Cassandra, y a qué costo.

**Qué no se puede concluir.**

- **No** se extrapola el throughput medido a la escala productiva. Una sola notebook comparte la CPU entre el generador, la API y las bases, y no hay red real.
- Lo que sí se puede razonar, sin medirlo, es la tendencia del mecanismo. La caché hace que las lecturas a Cassandra dependan de la cantidad de partidos activos por cada período del TTL, y no de la cantidad de lectores. Con más lectores del mismo partido, el ahorro relativo debería crecer. Esto es un **razonamiento de diseño**, no un resultado medido.

## 4. Limitaciones del entorno y de la medición

- **Recursos compartidos.** El generador, la API, Cassandra y Redis compiten por la misma CPU. Una mejora de la API también libera CPU para las bases, y viceversa.
- **Una sola corrida por modo.** No se estima la variabilidad entre corridas repetidas. Si el tiempo lo permite, repetir cada modo y comparar la dispersión.
- **Diferencias de condiciones.** Pueden variar la temperatura, el ahorro de energía y otras aplicaciones abiertas. Anotar en `linea_base.md` cualquier diferencia conocida entre las corridas.
- **`nodetool`.** Sus contadores son del nodo completo para esa tabla. Si otro proceso escribiera en la tabla durante la prueba, la conciliación lo mostraría como diferencia. Los percentiles de `tablehistograms` son del período reciente del nodo, no exactamente de la ventana de la prueba.
- **Frescura.** El atraso máximo de 2 s es un límite de diseño (el TTL). No se midió cuánto tarda un comentario en verse.
- **Estado en Redis.** La caché comparte instancia con las sesiones del Hito 7. Si hubiera sesiones cargadas en volumen, la presión de memoria sería distinta.
- **Clientes de la base.** Si la API usara `cqlsh` en lugar del driver nativo, las latencias absolutas no son representativas de un despliegue real (ver H0 en `hipotesis_y_optimizacion.md`).
