# Guion de la defensa ante la FIFA (20 minutos, RF13, RNF12)

> **Versión final (27/11):** la defensa se da con [`presentacion_final.pptx`](presentacion_final.pptx) y el speech completo palabra por palabra, con el banco de preguntas, está en [`speech_defensa_final.docx`](speech_defensa_final.docx). Reparto: Fermín 0-5 (problema, arquitectura, MongoDB, Neo4j e IRIS), Fran 5-10 (Cassandra, Redis, InfluxDB, CAP y comparación relacional), demo en vivo 10-15 ([`demo.md`](demo.md)) y Rodrigo 15-20 (observabilidad, evidencia y cierre). Lo de abajo es el guion anterior, que sigue valiendo como resumen de contenidos.

**Pregunta central:** *¿Por qué esta combinación de modelos, estructuras, estrategias de distribución y mecanismos de observabilidad es adecuada para el Fixture Mundial 2030 bajo las condiciones planteadas?*

**Regla de la exposición:** se defienden **las bases y las decisiones**; las herramientas (Grafana, Postman, Swagger) solo muestran evidencia (Clase 14). Cada número que se dice tiene que estar en el repositorio.

**Reparto sugerido** (los tres conocen todo el trabajo y pueden responder sobre cualquier módulo, como exige la consigna):

| Integrante | Bloques | Bases que presenta |
| :--- | :--- | :--- |
| Fermín | Inicio, Arquitectura y Cierre | MongoDB, Neo4j, IRIS |
| Fran | Decisiones de distribución y consistencia | Cassandra, Redis, InfluxDB |
| Rodrigo | Operación (demo) y Evidencia | API, Prometheus y Grafana |

El reparto se puede cambiar; lo que importa es que cada bloque tenga un responsable y que los tiempos se respeten.

## Tiempos

| Minuto | Bloque | Quién | Recurso |
| :--- | :--- | :--- | :--- |
| 0:00 - 1:30 | Inicio | Fermín | Diapositivas 1-2 |
| 1:30 - 5:00 | Arquitectura | Fermín | Diapositivas 3-4 |
| 5:00 - 9:00 | Decisiones | Fran | Diapositivas 5-7 |
| 9:00 - 14:00 | Operación | Rodrigo | Postman + Grafana en vivo ([demo.md](demo.md)) |
| 14:00 - 17:30 | Evidencia | Rodrigo | Diapositivas 8-9 + tablero |
| 17:30 - 19:30 | Cierre | Fermín | Diapositivas 10-11 |
| 19:30 - 20:00 | Margen | — | — |

Las preguntas de la FIFA pueden llegar en cualquier momento: el que presenta el bloque responde, o deriva al dueño del módulo. Respuestas preparadas en [`../docs/defensa_final.md`](../docs/defensa_final.md).

## 0:00 - 1:30 · Inicio (Fermín)

- **El problema:** el Mundial 2030 junta 64 selecciones, más de mil jugadores, partidos en seis países y millones de hinchas a la vez. Cada tipo de dato tiene un patrón de acceso distinto.
- **Las condiciones** del Hito 1: p95 menor a 100 ms, 99,99 % de disponibilidad, 2-3 M de sesiones, 1 M+ comentarios por partido y 10 M+ puntos de estadísticas.
- **La decisión general:** una arquitectura políglota. Seis modelos, cada uno elegido por el patrón de acceso de su dato, detrás de una sola API.
- **Frase de cierre del bloque:** *"No elegimos seis bases porque sí: cada una resuelve un acceso que las otras harían caro. Y les vamos a mostrar lo que cuesta."*

## 1:30 - 5:00 · Arquitectura (Fermín)

Recorrido por la diapositiva del mapa, una oración por base:
- **MongoDB:** fichas de equipos y jugadores. Documento validado con JSON Schema; el código FIFA es la clave que comparten todas las bases.
- **Neo4j:** partidos, sedes y eventos como grafo. El gol es un nodo que se recorre hasta el jugador y su equipo.
- **Cassandra:** comentarios masivos, particionados por partido y ventana de 5 minutos.
- **Redis:** sesiones con TTL y la caché del feed.
- **InfluxDB:** estadísticas por segundo, agregadas por ventanas.
- **IRIS:** el partido como objeto con reglas (estado, eventos y terna).
- **API:** una puerta de entrada con un adaptador por base. Si una base falla, solo fallan sus rutas.

Transición: *"Ahora, las decisiones que hacen que esto aguante un pico de gol."*

## 5:00 - 9:00 · Decisiones (Fran)

- **Cassandra en un pico de gol:**
  - La partición `(partido_id, ventana de 5 min)` convierte una partición ilimitada (unos 162 MiB en el partido extremo) en particiones acotadas (unos 15 MiB en el pico).
  - Medido: 2.688 particiones, máximo de 12.087 filas.
  - Riesgo declarado: el hotspot *dentro* de la ventana. Siguiente paso: ventana de 1 minuto o *shard*.
- **CAP por dato** (diapositiva del mapa CAP):
  - Información deportiva (MongoDB, Neo4j) es **CP**: un resultado oficial no puede leerse viejo.
  - Comentarios, sesiones y estadísticas son **AP**: el feed sigue aceptando comentarios aunque una región tarde en verlos, se acepta perder una sesión (el usuario se vuelve a autenticar) y la ingesta de estadísticas no se detiene.
- **Si se cae una región:** lo CP rechaza escrituras sin mayoría; lo AP sigue con las réplicas que quedan. En el laboratorio hay un solo nodo por base: **la replicación es diseño, no medición**, y lo decimos así.
- **Por qué no SQL:** para equipos y partidos SQL sería válido (Hito 1). Pero un motor relacional único concentra las escrituras del partido caliente en el mismo índice, no tiene TTL ni downsampling nativos y recorre relaciones con joins recursivos. Comparación completa en el Hito 12.

## 9:00 - 14:00 · Operación (Rodrigo)

Seguir [demo.md](demo.md):
1. **Flujo 1** (Postman): el mismo partido atravesando las seis bases. En cada request, decir qué base lo atiende y por qué.
2. **Flujo 2** (Grafana): carga mixta. Mostrar latencia p95 por base, aciertos de caché y escrituras por partido. Después, `docker stop fixture2030-redis`: la caché cae a 0 %, las lecturas van a Cassandra, `/sesiones` da 503 y el resto sigue en 200. El panel *Corte rápido* muestra unas 75 llamadas por segundo que la API ya no intenta contra Redis. Por último, `docker start`: a los 15 s Redis vuelve a verde.

Mensaje: *"La caída de una base degrada una funcionalidad; no tira el Fixture."*

## 14:00 - 17:30 · Evidencia (Rodrigo)

- **Prometheus:** 9 jobs y 13 targets (API, exporters, endpoints nativos y sondas), leídos cada 15 s; en la corrida final, 13/13 UP. Las métricas de infraestructura miden la base por dentro; las de aplicación, cómo la vive la API. Neo4j Community y Cassandra no exponen métricas internas: se miden con sondas y desde la API, y se dice.
- **Operación normal** (`evidencia/operacion_normal/20261126-054628/resumen.md`): 91,6 requests/s con 20 usuarios; p95 de 24 ms (SLO de 50 ms, SLA de 100 ms); 0 % de errores; caché con 96 % de aciertos. La base más rápida es Redis (p95 de 2,5 ms) y la más lenta InfluxDB (45,7 ms), porque agrega ventanas de tiempo.
- **Prueba controlada** (`evidencia/prueba_de_falla/20261126-054628/resumen.md`, diapositiva 9):
  - Redis cae bajo carga: 92,1 → 88,5 requests/s; p95 de 23,7 → 32,8 ms; caché de 96 % a 0 %; Cassandra pasa de 1,4 a 35,5 lecturas/s sin cambiar su p95.
  - Detección: la métrica a los +15 s; `BaseNoDisponible` crítica a los +90 s. Recuperación: +15 s después del `docker start`.
  - Cassandra cae: 503 solo en comentarios; Mongo, Neo4j e IRIS en 200; alerta crítica a los +85 s.
- **La mejora (RF12):** en la corrida 1, sin corte rápido, cada request esperaba 2,4 s a Redis caído: el throughput cayó de 53,6 a 9,4 requests/s. Con el corte rápido cae un 4 %. Lo encontramos gracias al monitoreo y lo medimos (`docs/limitaciones_y_evidencia.md` §4).
- **Alertas:** siete reglas, cada una con impacto, acción y razón del umbral. El SLO interno de 50 ms es más exigente que el SLA de 100 ms.
- **Medido y proyectado** (diapositiva): qué medimos (10,6 M de puntos, 1,1 M de comentarios, pruebas de carga y fallas) y qué es proyección (2-3 M de usuarios, multirregión, 99,99 %).

## 17:30 - 19:30 · Cierre (Fermín)

- **Por qué es adecuada:** cada dato está en el modelo que abarata su acceso dominante; la API aísla las fallas; el monitoreo permite ver qué base está afectada y decidir.
- **Trade-offs aceptados:**
  - seis motores para operar;
  - consistencia eventual donde el negocio la tolera;
  - sin transacciones entre motores;
  - dos bases sin métricas internas en el laboratorio.
- **Qué mejoraríamos:**
  - réplicas reales y prueba de caída de nodo;
  - exporter JMX para Cassandra;
  - ya hecho en este hito: corte rápido por base, sacado de la evidencia; falta un A/B limpio con `--sin-cortocircuito`;
  - un `/salud` liviano para balanceadores y una alerta de 5xx que exija un mínimo de tráfico;
  - conectar la caché de fichas del Hito 7 a la API.
- **Frase final:** *"No dijimos que la arquitectura sea perfecta. Les mostramos qué resuelve cada base, qué cuesta y cómo nos damos cuenta cuando algo falla."*

## Checklist del día

- [ ] `git push` hecho y capturas visibles en GitHub.
- [ ] Docker Desktop abierto, `iniciar_monitoreo --con-bases` corrido 10 minutos antes, `probar_iris` en OK y `verificar_targets` con 13/13 UP.
- [ ] API levantada con `.\monitoreo\scripts\iniciar_api_monitoreada.ps1` (credenciales del Hito 11, caché y corte rápido).
- [ ] Postman con `postman_demo_h13.json` importada; Grafana en *Last 15 minutes*.
- [ ] Presentación abierta (`presentacion.html`, se navega con las flechas).
- [ ] Ensayo cronometrado: si pasa de 20 minutos, recortar el Flujo 1 a 4 requests (Mongo, Neo4j, Cassandra, Redis).
