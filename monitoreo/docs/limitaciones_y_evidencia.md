# Limitaciones y evidencia (RF10, RF11, RF12)

Este documento separa tres cosas, como pide el hito:

- **Medido:** se corrió en el laboratorio y la evidencia está en `../evidencia/`.
- **Diseño:** decisión de arquitectura argumentada, sin ejecutar en el laboratorio.
- **Proyección:** cifra del escenario FIFA (Hito 1) que no se puede medir acá.

Todas las cifras de este documento salen de los informes generados por `scripts/ejecutar_prueba_controlada.py`. Ninguna se calculó a mano.

## 1. Corridas realizadas

En el repositorio quedan dos corridas: la final, que es la que se defiende, y la primera, que es el "antes" de la mejora. Las corridas intermedias, que validaron cada corrección, no se incluyen.

| Etiqueta | Qué corrió | Estado del laboratorio | Para qué sirve |
| :--- | :--- | :--- | :--- |
| `20261126-040222` (corrida 1) | Falla A (Redis) y B (Cassandra), **sin corte rápido** | IRIS no disponible para la API; error en el adaptador de Mongo | El "antes" de la mejora y los dos defectos encontrados |
| **`20261126-054628` (final)** | Operación normal 181 s, falla A y falla B | **6/6 bases, 13/13 targets UP, 7/7 sondas OK** | **La corrida que se defiende** |

Evidencia de la corrida final:

- Operación normal: [`../evidencia/operacion_normal/20261126-054628/resumen.md`](../evidencia/operacion_normal/20261126-054628/resumen.md)
- Pruebas de falla: [`../evidencia/prueba_de_falla/20261126-054628/resumen.md`](../evidencia/prueba_de_falla/20261126-054628/resumen.md)
- Targets: [`../evidencia/prometheus_targets.md`](../evidencia/prometheus_targets.md)
- Capturas: `../evidencia/dashboards/operacion_20261126-054628_*.png` y `prueba_20261126-054628_*.png`
- Log de la corrida: `../evidencia/resultados_sin_secretos/ejecucion_20261126-054628.log`

Condiciones de todas las corridas: 20 usuarios virtuales en lazo cerrado, con una pausa de 0,1 a 0,3 s entre requests. La mezcla de operaciones toca las seis bases y la caché del Hito 12 está encendida. Las escrituras van solo a partidos de laboratorio `H13-<etiqueta>-P1/P2`. Ningún volumen se borró (RNF11).

## 2. RF11: métricas frente a los objetivos del TPO

| Objetivo del TPO | Métrica (consulta de `metricas_y_consultas.md`) | Medido en la corrida final | Qué no se puede afirmar |
| :--- | :--- | :--- | :--- |
| **Concurrencia** | Usuarios del generador; errores de conexión del cliente | 20 usuarios simultáneos, 0 errores de conexión en 16.607 requests | Millones de usuarios: es **proyección** (Hito 1). |
| **Throughput** | Q2, `rate(fixture_api_requests_total[1m])`; Q6, operaciones por base | API: **91,6 requests/s**. Por base: Redis 42,2, Cassandra 15,5, Mongo 13,9, Neo4j 9,0, InfluxDB 7,1 e IRIS 6,5 operaciones/s | 100.000+ requests/s es **proyección**. Una sola instancia de la API en una sola máquina. |
| **Latencia** | Q3, p50/p95/p99 de la API; Q5, p95 por base | API: p50 4,5 ms, **p95 24,0 ms**, p99 44,4 ms. Cumple el SLO de 50 ms y el SLA de 100 ms. Más lenta, InfluxDB: p95 45,7 ms (agregaciones). Más rápida, Redis: p95 2,5 ms. | Latencia entre regiones: **diseño**. |
| **Disponibilidad** | Q1, `up`/`probe_success`; Q6, `fixture_dependencia_disponible`; Q4, 5xx | 13/13 targets UP, 6/6 bases, 0 % de 5xx. Con Redis caído, 5 % de 5xx: solo sesiones, el resto siguió en 200. Con Cassandra caída, solo comentarios dio 503. | 99,99 % anual: **proyección**. Un nodo por base: la caída de una réplica o de una región es **diseño**. |
| **Distribución** | `fixture_comentarios_creados_total{partido}`; lecturas que llegan a Cassandra | 2 partidos × 2 ventanas de 5 min escritos (4 particiones nuevas). Con caché, solo 1,4 lecturas/s llegan a Cassandra. | Un nodo de Cassandra: no hay reparto real entre nodos. El reparto por `(partido_id, ventana)` es **diseño** y medido en el Hito 6. |
| **Recuperación** | Tiempo hasta `redis_up = 1`, hasta disponible para la API y hasta caché ≥ 80 % | Redis: la API lo ve disponible **+15 s** después del `docker start`; la caché vuelve a ≥ 80 % a los +45 s. Cassandra: disponible a los +56 s, comentarios en 200 a los +41 s. | Recuperación de una región o de un nodo con réplicas atrasadas: **diseño**. |

Comparación entre bases (RF7): el orden de latencia Redis < Mongo < IRIS < Neo4j < Cassandra < InfluxDB coincide con el tipo de acceso de cada una. Redis y Mongo leen por clave; Neo4j recorre relaciones; Cassandra lee una partición ordenada; InfluxDB agrega una ventana de tiempo. Cassandra es la base con más operaciones después de Redis porque sostiene el feed de comentarios, que es la funcionalidad más usada en la mezcla.

## 3. Pruebas de falla (RF10)

### A. Redis cae bajo carga

| Indicador (Prometheus) | Normal | Redis caído | Recuperación |
| :--- | --: | --: | --: |
| Requests/s de la API | 92,1 | 88,5 | 91,1 |
| p95 de la API | 23,7 ms | 32,8 ms | 26,9 ms |
| p95 de GET comentarios | 9,7 ms | 24,9 ms | 14,5 ms |
| Lecturas que llegan a Cassandra (/s) | 1,4 | 35,5 | 1,4 |
| Aciertos de caché | 96,2 % | 0 % | 96,2 % |
| Errores 5xx | 0 % | 5,0 % | 0 % |
| Llamadas a Redis evitadas por el corte rápido (/s) | — | 75,3 | 0 |

**Lectura:** con Redis caído se pierden las sesiones: son el 5 % de 5xx, todas 503 en `/sesiones`. También se pierde la caché, así que las lecturas de comentarios pasan a Cassandra: de 1,4 a 35,5 por segundo. Cassandra las absorbió sin cambiar su p95 (24,2 ms). El throughput casi no cayó. La detección y las alertas están en `alertas_y_umbral.md` ("Tiempos medidos"): la métrica vio la caída a los +15 s y `BaseNoDisponible` pasó a firing a los +90 s.

### B. Cassandra cae (sin carga)

| Fuente | Ruta | Antes | Cassandra caída | Después |
| :--- | :--- | :--- | :--- | :--- |
| Cassandra | `/partidos/F2030-063/comentarios` | 200 | **503** DEPENDENCY_UNAVAILABLE | 200 |
| MongoDB | `/equipos/ARG` | 200 | 200 | 200 |
| Neo4j | `/partidos/F2030-001/eventos` | 200 | 200 | 200 |
| IRIS | `/partidos/F2030-001/detalle` | 200 | 200 | 200 |
| Redis | `/sesiones/S0001` | 404 | 404 | 404 |

La caída de un motor degrada **una** funcionalidad y no el Fixture: es la decisión de un adaptador por base del Hito 10, ahora demostrada. La API vio la caída a los +10 s y `BaseNoDisponible{fuente="cassandra"}` pasó a firing a los +85 s. Después del `docker start`, Cassandra tardó unos 40 s en aceptar consultas.

El 404 de `/sesiones/S0001` no es un error: la sesión de laboratorio del Hito 7 venció por TTL. Sirve igual para la demostración, porque el contrato distingue la sesión vencida (404) de Redis caído (503).

## 4. RF12: mejora transversal (corte rápido por base)

### El problema, visto en la corrida 1

En Windows, una conexión a una base detenida no falla al instante: el rechazo tarda unos **2,4 s**. Sin protección, cada request que tocaba Redis caído pagaba esos 2,4 s y ocupaba un hilo de la API. Así se veía en la corrida 1:

| Indicador, fase de falla A | Corrida 1, sin corte rápido | Corrida final, con corte rápido |
| :--- | --: | --: |
| Requests/s (normal → falla) | 53,6 → **9,4** (−82 %) | 92,1 → **88,5** (−4 %) |
| p95 de las llamadas a Redis | **2.425 ms** | 2,4 ms (se rechaza sin intentar) |
| p95 de GET comentarios | **4.875 ms** | 24,9 ms |
| p95 de la API | 4.684,8 ms | 32,8 ms |
| Lecturas que llegan a Cassandra (/s) | 3,7 | 35,5 |

La última fila importa: sin corte rápido, las lecturas casi no llegaban a Cassandra porque la API estaba bloqueada esperando a Redis. El cuello de botella no era Cassandra sino **el tiempo de falla de la conexión**.

### El cambio

`api/app/core/cortocircuito.py`: cuando una conexión a una base falla, la API deja de intentar con esa base durante `CORTOCIRCUITO_S` segundos (10 por defecto).

- Mientras el corte está abierto, la ruta de esa base responde 503 enseguida.
- La caché no responde 503: la API la saltea y lee directo de Cassandra.
- Pasado ese tiempo, deja pasar un solo intento de prueba. Si sale bien, el corte se cierra.
- Solo abren el corte los errores de **conexión**. Un dato inválido (por ejemplo, un `comentario_id` mal formado) no lo abre.

La mejora es observable: `fixture_cortocircuito_abierto{fuente}` y `fixture_cortocircuito_rechazos_total{fuente}`, en el panel *Corte rápido* del tablero.

### Resultado y honestidad del antes/después

- El "antes" es la corrida 1, que además tenía IRIS no disponible y el error de Mongo. Por eso su fase normal ya estaba degradada (p95 de 1.444 ms, por las esperas a IRIS). Las filas que aíslan el efecto son las de Redis y GET comentarios: solo dependen de Redis.
- Para un A/B limpio sobre el mismo código: `.\monitoreo\scripts\ejecutar_todo_h13.ps1 --sin-cortocircuito` (`CORTOCIRCUITO_S=0`). No lo corrimos para la entrega.
- **Costo de la mejora:** durante hasta 10 s después de que una base vuelve, la API puede seguir respondiendo 503 hasta el intento de prueba. Además, con Redis caído, Cassandra recibe 25 veces más lecturas: en un pico de gol real eso es el riesgo que vigila `CacheComentariosDegradada`.

## 5. Defectos y hallazgos que salieron del monitoreo

| Hallazgo | Cómo se vio | Corrección |
| :--- | :--- | :--- |
| El adaptador de Mongo buscaba por `_id`, pero el modelo del Hito 4 usa `codigo` | Respuestas 500 en las rutas de Mongo durante la corrida 1 (parte del 12 % de 5xx; el resto eran 503 de IRIS) y 868 errores de conexión del cliente, porque cada 500 cerraba la conexión | Búsqueda por `codigo` o `_id` y proyección con `$ifNull`. En la corrida final: 0 errores de conexión. |
| Una conexión rechazada tarda 2,4 s en Windows | p95 de Redis de 2.425 ms con Redis caído | Corte rápido (sección 4) |
| Windows reserva un rango de puertos que incluye el 52773 de IRIS | `ports are not available` al crear el contenedor | IRIS en 1972 y 18773 (`compose/iris-puertos-windows.yml`). Prometheus la lee por la red de Docker. |
| IRIS Community obliga a cambiar la contraseña de `_SYSTEM` | `Access Denied` de la API, con el target `iris` en UP | La API toma la contraseña de `conectividad/config/configuracion.env` (Hito 11, fuera de Git). Se agregó `probar_iris`. |
| Las sondas TCP salían por IPv6 | `probe_success = 0` con la base sana | `preferred_ip_protocol: ip4` en `blackbox.yml` |
| Prometheus y blackbox no tomaban la configuración nueva | Reglas o módulos viejos después de editar | Los scripts llaman a `/-/reload` |
| El enmascarado tapaba valores públicos de laboratorio | `fixture2030-redis` aparecía como `***-redis` en la evidencia | Corregido en la evidencia de la corrida final y en `enmascarar()` |

Dos de estos defectos (Mongo y el tiempo de falla) no se veían con la prueba funcional de los Hitos 10 y 12: aparecieron recién con métricas bajo carga y con una base caída.

## 6. Análisis secundario: `/salud`

`/salud` consulta las seis bases **una después de otra** y no pasa por el corte rápido. Es a propósito: su función es probar de verdad cada conexión. La consecuencia es que, con una base caída, tarda al menos lo que tarde esa conexión en fallar (unos 2,4 s en Windows). No lo medimos aislado.

En producción conviene separar dos chequeos: uno liviano ("la API está viva"), para un balanceador con timeout corto, y uno profundo (el actual), para diagnóstico. El monitoreo no depende de `/salud`: usa el chequeo en segundo plano cada 15 s (`fixture_dependencia_disponible`), que explica los +10 a +15 s de detección.

## 7. Límites de la instrumentación

- **Una sola máquina** (Docker Desktop). Las bases, la API, el monitoreo y el generador de carga comparten CPU, así que las latencias absolutas dependen de la máquina.
- **Un nodo por base.** No hay métricas de replicación (lag, elecciones, quórum) porque no hay réplicas.
- **Neo4j Community** no expone métricas internas (son de Enterprise) y **Cassandra** no tiene exporter JMX. Se observan con sondas y desde la API. En Docker Desktop, la sonda TCP de Cassandra puede aceptar la conexión antes de que el nodo esté listo; por eso la señal confiable es la de la API.
- **Resolución de 15 s.** Los tiempos de detección tienen un error de hasta un intervalo.
- **Percentiles aproximados.** Los de Prometheus salen de buckets de histograma. Los del cliente son exactos, y los dos coinciden (p95 de 24,0 contra 24,23 ms).
- **Contadores en memoria.** Se reinician con la API; `rate()` lo tolera. Hay una sola instancia de la API.
- **Sin notificaciones reales.** Alertmanager agrupa y enruta, pero no tiene canal de mail ni de chat.
- **Carga sintética.** La mezcla es fija y no reproduce un pico de gol real ni la distribución horaria del torneo.
- **Trazabilidad.** El `metadata.json` de cada corrida guarda el commit con el que corrió. El historial se compactó antes de publicarlo:
  - La corrida final corrió sobre `85e91ae`, cuyo código es idéntico al del commit `127501a`.
  - La corrida 1 corrió sobre una versión previa a las correcciones (sin corte rápido y con el error de Mongo), que no quedó en el historial. El comportamiento sin corte rápido se reproduce con `--sin-cortocircuito`.
  - La corrida final marca `cambios_sin_commit_en_api_o_monitoreo: true` porque contaba la propia evidencia todavía sin commitear. Desde esta entrega, la evidencia ya no cuenta para ese indicador.

## 8. Medido, diseño y proyección

| Afirmación | Tipo | Dónde está |
| :--- | :--- | :--- |
| p95 de la API de 24 ms con 20 usuarios y 0 % de errores | Medido | `operacion_normal/20261126-054628` |
| Una base caída degrada una sola funcionalidad | Medido | `prueba_de_falla/20261126-054628`, B |
| Detección en +10 a +15 s; alerta crítica en +85 a +90 s | Medido | ídem y `alertas_y_umbral.md` |
| El corte rápido mantiene el 96 % del throughput con Redis caído | Medido | Sección 4 |
| La caché evita el 96 % de las lecturas a Cassandra | Medido (también en el Hito 12: 98 %) | ídem |
| Partición `(partido_id, ventana)` acotada en un pico de gol | Diseño, con medición del Hito 6 | Hito 6 |
| Lo deportivo CP y lo social AP entre regiones | Diseño | Hito 3 y `decisiones_de_arquitectura.md` |
| Caída de una región sin perder comentarios | Diseño | ídem |
| 2-3 M de usuarios, 100.000+ requests/s, 99,99 % de disponibilidad | Proyección | Hito 1 |
