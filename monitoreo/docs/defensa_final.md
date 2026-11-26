# Defensa final ante la FIFA: respuesta central y preguntas preparadas

## La pregunta central

> *¿Por qué esta combinación de modelos, estructuras, estrategias de distribución y mecanismos de observabilidad resulta adecuada para el Fixture Mundial 2030 bajo las condiciones planteadas?*

**Respuesta en tres oraciones.**
1. Porque cada dato del Fixture está en el modelo que abarata su acceso dominante: documento para la ficha, grafo para el recorrido, partición por ventana para el feed masivo, clave/valor con TTL para la sesión, serie temporal para la estadística y objeto con reglas para el partido. La consistencia se eligió por dato: CP para lo deportivo y AP para lo social y lo efímero.
2. Porque la integración por una API con un adaptador por base y el corte rápido aíslan las fallas: en las pruebas de este hito, la caída de Redis o de Cassandra degradó solo su función y el resto del Fixture siguió respondiendo.
3. Porque la observabilidad muestra qué base está afectada, en cuánto tiempo y qué decisión tomar. Además, nos llevó a corregir dos defectos reales y a una mejora medida.

Los límites también se dicen: todo corre en una máquina y con un nodo por base. La replicación y la escala de millones de usuarios son diseño, no medición.

## Pitch de un minuto (por si piden un resumen)

"El Fixture tiene datos con necesidades opuestas: millones de comentarios que se escriben en ráfagas, sesiones que vencen, estadísticas por segundo, relaciones que se recorren y un partido con reglas. Ninguna base sola hace barato todo eso, así que usamos seis, cada una para lo que mejor resuelve, y una API que las integra con identificadores comunes. Para el pico de un gol, Cassandra reparte los comentarios por partido y ventana de 5 minutos, y Redis evita que el 98 % de las lecturas llegue a Cassandra. Medimos con Prometheus y Grafana: tiramos Redis y Cassandra bajo carga, vimos qué se degradaba y en cuánto tiempo nos enterábamos. Con esa evidencia agregamos un corte rápido que hizo que, con Redis caído, la API mantuviera el 96 % de su throughput; antes caía a menos de un quinto. No prometemos lo que no medimos: la parte multirregión es diseño."

## Cifras de la corrida final para tener a mano (20261126-054628)

Todos los integrantes tienen que poder decirlas sin mirar. El detalle está en `limitaciones_y_evidencia.md`.

| Qué | Cifra |
| :--- | :--- |
| Estado del laboratorio | 6/6 bases disponibles, 13/13 targets UP, 7/7 sondas OK |
| Operación normal (20 usuarios, 3 min) | 91,6 requests/s; p95 de 24 ms (SLO de 50, SLA de 100); 0 % de 5xx; caché con 96 % de aciertos |
| Base más rápida y más lenta (p95) | Redis 2,5 ms; InfluxDB 45,7 ms (agrega ventanas de tiempo) |
| Redis caído bajo carga | 92 → 88,5 requests/s; solo sesiones da 503 (5 %); Cassandra pasa de 1,4 a 35,5 lecturas/s y su p95 no cambia |
| Detección | La métrica ve la caída a los 10-15 s; la alerta crítica llega a los 85-90 s (`for: 1m`) |
| Recuperación | Redis: 15 s después del `docker start`; Cassandra: unos 40-56 s (lo que tarda en arrancar) |
| Mejora | Corte rápido: sin él, 2,4 s por request esperando a una base caída |

## Preguntas que la FIFA podría hacer (sección 6.5 y Clase 14)

| Pregunta | Respuesta corta | Evidencia |
| :--- | :--- | :--- |
| **¿Por qué eligieron este modelo para este tipo de dato?** | Por el acceso dominante de cada dato, no por la tecnología. Ejemplo: los comentarios se escriben en ráfagas y se leen "los últimos N del partido". Eso es una partición acotada con orden por tiempo (Cassandra), no un documento ni un grafo. | `docs/decisiones_de_arquitectura.md` §2 |
| **¿Qué consulta sería costosa con otra estructura?** | "Goleadores con su equipo" en documentos: varias consultas y un join en la aplicación; en el grafo es un recorrido de 2 saltos. "Posesión promedio cada 5 min" en SQL: GROUP BY sobre millones de filas sin retención. "Últimos 20 comentarios" con la partición solo por `partido_id`: una partición de 162 MiB. | Hitos 5, 8 y 6 |
| **¿Cómo se distribuyen los datos?** | Cassandra: partición `(partido_id, ventana)`, réplicas por región. Redis: por usuario. Mongo: sin particionar, réplica completa por región (volumen chico). InfluxDB: base viva con retención y resumen de 1 minuto sin expiración. En el laboratorio, un nodo por base. | §2 de decisiones; Hito 3 |
| **¿Cómo escala Cassandra en un pico de gol?** | La ventana de 5 minutos acota cada partición: unas 93.000 filas o 15 MiB en el pico del partido extremo [diseño]; 2.688 particiones con un máximo de 12.087 filas [medido]. El riesgo que queda es el hotspot dentro de la ventana; el umbral para revisarlo es 100.000 filas o 500 escrituras/s. Las lecturas repetidas las absorbe la caché: 98 % de aciertos en el Hito 12. | Hitos 6 y 12 |
| **¿Qué sucede si se cae un nodo o una región?** | Con réplicas: lo CP (información deportiva) deja de aceptar escrituras sin mayoría; lo AP (comentarios, sesiones, estadísticas) sigue con las réplicas que quedan. Medido en el laboratorio, la caída de una base entera: con Cassandra detenida, solo los comentarios dieron 503; fichas (Mongo), eventos (Neo4j) y detalle del partido (IRIS) siguieron en 200, y la alerta crítica llegó a los 85 s. | Prueba B: `evidencia/prueba_de_falla/20261126-054628/resumen.md` |
| **¿Qué garantía de consistencia necesita este módulo?** | Deportiva: fuerte (un resultado oficial no se lee viejo). Partido en IRIS: invariantes al guardar. Comentarios, sesiones y estadísticas: eventual. | Decisiones §2, Hito 3 |
| **¿Qué parte de la respuesta puede ser eventual?** | El feed (orden y visibilidad entre regiones, más hasta 2 s de caché), una sesión (se puede perder: el usuario se vuelve a autenticar) y los puntos de estadísticas tardíos. **No** pueden ser eventuales el resultado, los goles ni el estado del partido. | Hitos 3, 7, 8 y 12 |
| **¿Dónde se encuentra el cuello de botella?** | En el pico, las lecturas repetidas de la misma partición: lo resolvió la caché del Hito 12. Ante fallas, este hito encontró otro: el tiempo que tarda en fallar una conexión a una base caída (unos 2,4 s en Windows). Sin corte rápido, la API lo pagaba en cada request (53,6 → 9,4 requests/s con Redis caído). | Corrida 1 y mejora en `limitaciones_y_evidencia.md` |
| **¿Cómo distinguen que el problema está en la API y no en la base?** | Comparando dos histogramas: la latencia total de la API (Q3) y la de cada base medida alrededor de su adaptador (Q5). Si sube la de una base, es esa base; si sube la total y ninguna base, es la API (hilos, cola o serialización). El generador de carga, además, compara la latencia del cliente con `X-Duracion-ms`. | `docs/metricas_y_consultas.md` |
| **¿Qué métrica observarían primero ante un aumento de latencia?** | Primero la salud por base (¿hay alguna caída?); después la latencia p95 por base (¿cuál subió?); después los aciertos de caché (¿se está yendo todo a Cassandra?). | Tablero, filas 1, 4 y 5 |
| **¿Qué evidencia tienen de que la optimización funcionó?** | Caché (Hito 12): lecturas que llegaron a Cassandra de 24.469 a 456, y p95 de lecturas de 22 a 5 ms. Corte rápido (este hito): con Redis caído, el throughput pasó de caer un 82 % (53,6 → 9,4 requests/s) a caer un 4 % (92,1 → 88,5), y el p95 de leer comentarios, de 4,9 s a 25 ms. | Hito 12 `comparacion.md`; este hito `limitaciones_y_evidencia.md` |
| **¿Qué cambiarían si el tráfico se multiplica?** | Réplicas reales y consistencia por región como en el Hito 3; ventana de 1 minuto o *shard* en Cassandra si una partición pasa el umbral; más instancias de la API (no tiene estado, y Prometheus suma sus métricas); caché también para fichas y estadísticas; Redis separado para sesiones y caché. | Decisiones §3 |
| **¿Qué se perdería o retrasaría durante una falla?** | Redis: sesiones (reautenticar) y la caché (más carga en Cassandra). Cassandra: el feed mientras dure, salvo la página en caché durante 2 s. InfluxDB: puntos si no hay buffer de ingesta. Mongo, Neo4j e IRIS: sus rutas dan 503 hasta reiniciar. Nada se pierde de las bases sanas. | Decisiones §3, tabla de fallas |
| **¿Qué información no pueden afirmar porque no fue medida?** | 2-3 M de usuarios, 100.000+ requests/s, 99,99 % de disponibilidad, comportamiento multirregión, lag de réplicas y métricas internas de Neo4j y Cassandra. | `limitaciones_y_evidencia.md` §3 |
| **¿Qué costo operativo agrega mantener seis modelos?** | Seis motores para instalar, respaldar y actualizar; seis formas de monitorear (dos sin métricas propias en el laboratorio); seis modelos de consistencia; sin transacciones entre motores. Por eso cada motor tiene que justificarse por su acceso: el Hito 1 lo advirtió antes de elegir. | Decisiones §4 |
| **¿Por qué NO usaron SQL?** | SQL sería válido para equipos y partidos (volumen chico, Hito 1). Pero un motor relacional único concentra las escrituras del partido caliente en el mismo índice, no tiene TTL ni downsampling nativos y recorre relaciones con joins recursivos. Lo que SQL hace mejor (idempotencia, integridad y joins) se compensó con claves de negocio, validación y el Data Mart. | Hito 12 `comparacion_relacional.md` |

## Cómo responder una pregunta que no esperábamos

1. Decir qué base atiende ese dato y cuál es su acceso dominante.
2. Decir qué garantía tiene (CP o AP) y qué se resignó.
3. Mostrar una prueba: una request, un panel o un archivo del repositorio.
4. Si no se midió, decirlo así: *"eso es diseño, no lo medimos en el laboratorio"*.
