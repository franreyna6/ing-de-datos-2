# Alertas y umbrales operativos (RF9, sección 5.4)

Las reglas están en [`../prometheus/reglas-o-alertas.yml`](../prometheus/reglas-o-alertas.yml). Prometheus las evalúa cada 15 s y le delega el aviso a Alertmanager (http://localhost:9093), como muestra la Clase 14. Cada regla lleva en sus etiquetas y anotaciones los ocho datos que pide la sección 5.4. Este documento los explica y agrega **qué decisión habilita** cada alerta: una alerta que solo dice "CPU alta" no sirve.

## SLI, SLO y SLA en el Fixture (Clase 14)

| Concepto | Definición | En el Fixture 2030 |
| :--- | :--- | :--- |
| **SLI** (lo que se mide) | Indicador observable | Latencia p95 de la API (Q3), tasa de 5xx (Q4), disponibilidad de cada base (Q6), aciertos de caché (Q7) |
| **SLO** (el objetivo) | Meta interna sobre el SLI | p95 < 50 ms en el laboratorio; 5xx < 1 %; caché ≥ 80 % de aciertos |
| **SLA** (la promesa) | Compromiso contractual, con consecuencia si no se cumple | El del TPO frente a la FIFA (p95 < 100 ms y 99,99 % de disponibilidad, Hito 1). **No** se verifica en el laboratorio. |

El SLO de 50 ms es más exigente que el SLA de 100 ms a propósito: alertar al pasar el objetivo interno da margen para actuar antes de romper la promesa.

## Resumen

| Alerta | Severidad | Componente | Condición | Duración | Quién la atiende |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `BaseNoDisponible` | crítica | la base afectada | `fixture_dependencia_disponible == 0` | 1 min | Guardia de plataforma |
| `TasaErrores5xxAlta` | crítica | API | 5xx / total > 1 % | 1 min | Guardia de plataforma |
| `LatenciaAPIp95SobreSLO` | advertencia | API | p95 > 50 ms | 1 min | Responsable de la API |
| `CacheComentariosDegradada` | advertencia | Redis | aciertos < 80 % | 1 min | Responsable del módulo Redis |
| `RedisMemoriaAlta` | advertencia | Redis | memoria usada / máxima > 85 % | 2 min | Responsable del módulo Redis |
| `SondaExternaFallida` | advertencia | la base de la sonda | `probe_success == 0` | 1 min | Responsable del módulo |
| `TargetDeMonitoreoCaido` | advertencia | el target | `up == 0` (sin contar las sondas) | 1 min | Responsable de observabilidad |

Alertmanager agrupa por `alertname` y `componente`, manda las críticas a *guardia-plataforma* y las advertencias a *responsable-del-modulo*. Tiene una regla de inhibición: mientras una base está caída, no avisa además que la latencia empeoró, porque es consecuencia de lo mismo.

## Detalle de cada alerta

### 1. `BaseNoDisponible` — crítica

| Campo | Valor |
| :--- | :--- |
| Métrica evaluada | `fixture_dependencia_disponible{fuente}`: chequeo de protocolo de la API cada 15 s (ping a Redis, `SELECT release_version` a Cassandra, consulta mínima a cada base) |
| Condición | `== 0` |
| Duración mínima | 1 minuto (`for: 1m`) |
| Severidad | crítica |
| Componente afectado | la base indicada en `fuente` (MongoDB, Neo4j, Cassandra, Redis, InfluxDB o IRIS) |
| Impacto en el Fixture | Las rutas de esa base responden 503 y el resto sigue en 200, porque los adaptadores están separados (Hito 10). Por ejemplo, Cassandra caída deja sin comentarios pero no sin fichas ni estadísticas. Redis caído deja sin sesiones y sin caché, y las lecturas de comentarios pasan a Cassandra. |
| Acción | `docker ps --filter name=fixture2030`, `docker logs --tail 50 fixture2030-<base>`. Si está detenida, `docker start` (nunca `down -v`). Confirmar que vuelve a verde el panel *Estado de salud*. En producción: verificar que las réplicas restantes atienden (Hito 3) y escalar al responsable del módulo. |
| Razón del umbral | 1 minuto = 4 chequeos seguidos fallidos. Un timeout aislado no la dispara, y avisa antes de que un pico de gol acumule errores. Medido: +90 s con Redis y +85 s con Cassandra (ver "Tiempos medidos"). |
| Decisión que habilita | Saber **qué** base y **qué** funcionalidad están afectadas, y declarar el modo degradado en vez de tratarlo como caída total. |

Es la versión del Fixture del *"CRITICAL: Cassandra Node Down"* de la Clase 14, generalizada a las seis bases.

### 2. `TasaErrores5xxAlta` — crítica

| Campo | Valor |
| :--- | :--- |
| Métrica evaluada | `fixture_api_requests_total` por `estado` |
| Condición | `sum(rate(...{estado=~"5.."}[1m])) / sum(rate(...[1m])) > 0.01` |
| Duración mínima | 1 minuto |
| Severidad | crítica |
| Componente afectado | API (y la base detrás de la ruta que falla) |
| Impacto en el Fixture | Usuarios que no pueden publicar o leer comentarios, ver estadísticas o validar su sesión. |
| Acción | En el panel *Respuestas no exitosas* ver qué ruta y qué código; cruzar con *Estado de salud* (un 503 suele ser una base) y con los logs de la API por `request_id`. |
| Razón del umbral | En el Hito 12 la tasa de error medida fue 0 %. Un 1 % sostenido durante un minuto no es ruido. |
| Decisión que habilita | Distinguir un problema de una base (503 en una ruta) de un error de la API (500 en varias rutas). |

### 3. `LatenciaAPIp95SobreSLO` — advertencia

| Campo | Valor |
| :--- | :--- |
| Métrica evaluada | `fixture_api_request_duration_seconds` (histograma), p95 de todas las rutas |
| Condición | `histogram_quantile(0.95, sum by (le) (rate(..._bucket[1m]))) > 0.05` |
| Duración mínima | 1 minuto |
| Severidad | advertencia |
| Componente afectado | API |
| Impacto en el Fixture | Pantalla de partido lenta. En un pico de gol, las requests se acumulan en cola. |
| Acción | Mirar *Latencia p95 por base*: si una fuente subió, el problema es esa base (o su caché). Si ninguna subió, revisar la API. Revisar la tasa de aciertos de caché. |
| Razón del umbral | **Experimental.** En el Hito 12 el p95 medido dentro de la API fue de 16 a 26 ms con 40 a 60 usuarios. 50 ms es aproximadamente el doble: deja margen para la variación normal y marca una degradación real. Está por debajo del SLA de 100 ms del TPO. |
| Decisión que habilita | Actuar (caché, escalar la base lenta) antes de violar el SLA. |

### 4. `CacheComentariosDegradada` — advertencia

| Campo | Valor |
| :--- | :--- |
| Métrica evaluada | `fixture_cache_comentarios_total{estado}` |
| Condición | HIT / (HIT + MISS) < 0,8 |
| Duración mínima | 1 minuto |
| Severidad | advertencia |
| Componente afectado | Redis (caché del Hito 12) |
| Impacto en el Fixture | Las lecturas del feed vuelven a Cassandra: sube la latencia y la carga sobre la partición caliente del partido. Es el problema que resolvió el Hito 12, donde las lecturas que llegaban a Cassandra bajaron de 24.469 a 456. |
| Acción | Ver si Redis está disponible y su memoria. Confirmar que la API corre con `CACHE_COMENTARIOS_TTL_S > 0`. |
| Razón del umbral | El Hito 12 midió 0,98 de aciertos. Por debajo de 0,8, la caché dejó de cumplir su función. |
| Decisión que habilita | Anticipar la sobrecarga de Cassandra antes de que se vea en la latencia del usuario. |

### 5. `RedisMemoriaAlta` — advertencia

| Campo | Valor |
| :--- | :--- |
| Métrica evaluada | `redis_memory_used_bytes / redis_memory_max_bytes` (redis_exporter) |
| Condición | > 0,85 (y `maxmemory` configurado) |
| Duración mínima | 2 minutos |
| Severidad | advertencia |
| Componente afectado | Redis |
| Impacto en el Fixture | Con `maxmemory 100mb` y `volatile-lru` (Hito 7), al llegar al límite Redis desaloja claves con TTL, **incluidas sesiones vigentes**: es el riesgo observado y corregido en el Hito 7. Si no quedan claves con TTL, rechaza escrituras (OOM). |
| Acción | Ver desalojos (`redis_evicted_keys_total`) y claves por tipo. Revisar los TTL de la caché. Ampliar `maxmemory` o separar sesiones y caché en instancias distintas, como propone el Hito 7. |
| Razón del umbral | 85 % es el umbral de la Clase 14 (*"WARN: Redis Memory at 85%"*). Con 2 minutos se ignoran picos momentáneos. |
| Decisión que habilita | Ampliar la memoria antes de perder sesiones. |

### 6. `SondaExternaFallida` — advertencia

| Campo | Valor |
| :--- | :--- |
| Métrica evaluada | `probe_success` (blackbox_exporter: TCP a Cassandra, MongoDB, Neo4j e IRIS; PING a Redis; HTTP a Neo4j e InfluxDB) |
| Condición | `== 0` |
| Duración mínima | 1 minuto |
| Severidad | advertencia |
| Componente afectado | la base de la sonda (`componente`) |
| Impacto en el Fixture | Confirma, desde fuera de la API, que la base no acepta conexiones. |
| Acción | Leer el error del target en `/targets`. Si falla la sonda pero no `BaseNoDisponible`, el problema está en el camino de red y no en la base. |
| Razón del umbral | Mismo criterio que `BaseNoDisponible`, para poder comparar las dos vistas. |
| Decisión que habilita | Separar "la base cayó" de "no llego a la base". |

### 7. `TargetDeMonitoreoCaido` — advertencia

| Campo | Valor |
| :--- | :--- |
| Métrica evaluada | `up` (generada por Prometheus), sin las sondas |
| Condición | `== 0` |
| Duración mínima | 1 minuto |
| Severidad | advertencia |
| Componente afectado | el exporter o endpoint (`job`) |
| Impacto en el Fixture | Se pierde visibilidad: no significa que la base esté caída, sino que no se puede medir. |
| Acción | Ver el README, sección "Investigar un target DOWN". |
| Razón del umbral | 4 scrapes fallidos seguidos. |
| Decisión que habilita | No confundir un problema del monitoreo con un problema de la plataforma. |

## Tiempo de detección esperado

Una alerta con `for: 1m` sobre un chequeo de 15 s tarda, desde la caída, entre 1 y 1,5 minutos en pasar a firing. Se suman el próximo chequeo (hasta 15 s), el próximo scrape (hasta 15 s), la evaluación (hasta 15 s) y el minuto de `for`. Los tiempos **medidos** están en el informe de la prueba controlada y en [`limitaciones_y_evidencia.md`](limitaciones_y_evidencia.md).

## Tiempos medidos (corrida final 20261126-054628)

Tiempos desde el `docker stop`, con resolución de 15 s. Fuente: `../evidencia/prueba_de_falla/20261126-054628/resumen.md` (series `ALERTS` de Prometheus).

| Evento | Redis caído bajo carga (A) | Cassandra caída (B) |
| :--- | --: | --: |
| La métrica ve la caída (`redis_up`, chequeo de la API) | +15 s | +10 s |
| `SondaExternaFallida` en firing | +75 s | +70 s |
| `BaseNoDisponible` en firing | +90 s | +85 s |
| `CacheComentariosDegradada` en firing | +90 s | — |
| `TasaErrores5xxAlta` en firing | +105 s (sesiones con 503) | no llegó a firing |
| La métrica ve la recuperación, desde el `docker start` | +15 s | +56 s (arranque de Cassandra) |

Las cuatro alertas de A cayeron dentro de la ventana esperada de 1 a 1,5 minutos. La única que no se disparó con Redis caído fue `LatenciaAPIp95SobreSLO`: el p95 subió de 23,7 a 32,8 ms, por debajo de los 50 ms, gracias al corte rápido. Sin él (corrida 1), el p95 llegó a 4,7 s.

**Lo que aprendimos de los umbrales:**

- `TasaErrores5xxAlta` pasó a *pending* durante B sin carga: con pocas requests, unas pocas respuestas 503 ya superan el 1 %. En producción conviene exigir además un mínimo de tráfico, por ejemplo `and sum(rate(fixture_api_requests_total[1m])) > 1`. No lo cambiamos para no alterar la regla después de medir.
- `SondaExternaFallida` llega antes que `BaseNoDisponible` porque la sonda no espera al chequeo de la API. Las dos juntas confirman que el problema es la base y no el camino de red.
