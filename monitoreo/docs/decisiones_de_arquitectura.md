# Decisiones de arquitectura del Fixture 2030 (RF14, RF15, sección 6.4)

Este documento reúne, en un solo lugar, **por qué cada dato vive en la base en la que vive** y qué consecuencias tiene esa elección. Es la base de la defensa: la Clase 14 lo resume en *"No defienden el código, DEFIENDEN LAS BASES"*. Cada afirmación remite al hito y al documento donde se tomó la decisión, o a la evidencia donde se midió.

Convención: **[medido]** = observado en una corrida con evidencia en el repositorio. **[diseño]** = decisión o estimación documentada, no medida. **[proyección]** = lo que haría falta en producción y no existe en el laboratorio.

## 1. La decisión general

El Hito 1 identificó nueve tipos de datos con patrones de acceso incompatibles entre sí:
- equipos y jugadores: chicos, fijos y de lectura alta;
- eventos y comentarios: ráfagas de escritura masiva (1 M+ comentarios por partido);
- sesiones: 2-3 M simultáneas, con validación en menos de 1 ms y vencimiento;
- estadísticas: más de 10 M de puntos por partido, que se agregan por tiempo;
- relaciones que se recorren: equipo → partido → evento → jugador.

La conclusión del Hito 1 fue que **ningún motor único sostiene a la vez esquemas heterogéneos, relaciones complejas, escritura masiva en tiempo real y agregación temporal bajo p95 < 100 ms y 99,99 % de disponibilidad**. Por eso, una arquitectura políglota: cada dato en el modelo que mejor atiende su patrón de acceso. El mismo Hito 1 dejó escrito el costo: *"sumar un motor implica más infraestructura para instalar, mantener y monitorear"*. Este hito lo hace visible: siete targets, tres exporters y dos bases sin métricas propias.

| Dato | Modelo | Motor | Hito | Patrón de acceso que decidió |
| :--- | :--- | :--- | :--- | :--- |
| Equipos y jugadores | Documental | MongoDB | 4 | Ficha completa en una lectura, estructura anidada, esquema validado |
| Partidos, sedes, eventos y sus relaciones | Grafo | Neo4j | 5 | Recorridos de 2 o más saltos (gol → jugador → equipo) |
| Comentarios en vivo | Tabular (columnar) | Cassandra | 6 | Escritura masiva sostenida por partido y lectura del feed reciente |
| Sesiones y caché | Clave/valor | Redis | 7, 12 | Lectura por clave en memoria con vencimiento (TTL) |
| Estadísticas en vivo | Series temporales | InfluxDB | 8 | Ingesta por segundo y agregación por ventanas |
| Partido como entidad con reglas | Objetos persistentes | IRIS | 9 | Estado, eventos dependientes e invariantes aplicadas al guardar |
| Acceso de las aplicaciones | — | API FastAPI | 10 | Una puerta de entrada, un adaptador por base |

## 2. Cada base, con las diez preguntas de la sección 6.4

### 2.1 MongoDB — equipos y jugadores (Hito 4)

| Pregunta | Respuesta |
| :--- | :--- |
| 1. Qué dato almacena | 64 selecciones y 1.024 jugadores, con director técnico como subdocumento y colores como array |
| 2. Qué accesos motivaron la elección | "Ficha de un equipo o jugador", "plantel de un equipo", "top N por confederación". Mucha lectura y casi ninguna escritura (Hito 1). |
| 3. Modelo | Documental. Puntaje 4,10 en la matriz del Hito 2. |
| 4. Estructura implementada | Dos colecciones con **referencia** (`jugadores.equipoCodigo` → `equipos.codigo`), no embebidas. Validación **JSON Schema estricta** (`validationAction: "error"`). Doble identificador: `_id` más un `codigo` de negocio (código FIFA; `ARG-10-xxxxxx` para jugadores), que reutilizan Neo4j, Cassandra, InfluxDB e IRIS. Siete índices, cada uno atado a una consulta (regla ESR). |
| 5. Carga y recuperación | Carga idempotente con `bulkWrite` + `upsert` por `codigo`; recuperación por `findOne` sobre índice único. API: `GET /equipos/{codigo}` y `/jugadores`. |
| 6. Escalado y distribución | **Sin particionar** (volumen fijo y chico); réplica completa por región (Hito 3) [proyección]. Si crecieran los históricos, la shard key natural sería `equipoCodigo`. |
| 7. Consistencia | Subsistema **CP** del Hito 3: escritura confirmada por mayoría de réplicas. Un resultado oficial no puede leerse desactualizado. |
| 8. Ante una falla | Las rutas de equipos y jugadores dan 503; el resto del Fixture sigue funcionando. En producción, con réplicas, se elige otro primario [proyección]. |
| 9. Trade-off | Sin integridad referencial automática (se verifica al cargar: 0 huérfanos); dos identificadores por documento. |
| 10. Evidencia | 0 errores de schema, 0 huérfanos y 0 duplicados sobre 1.024 jugadores; `explain()` antes y después de los índices (`mongodb/evidencia/`). En este hito: `mongodb_up`, opcounters y latencia de `obtener_equipo`. |

### 2.2 Neo4j — partidos, sedes y eventos como grafo (Hito 5)

| Pregunta | Respuesta |
| :--- | :--- |
| 1. Qué dato almacena | 64 equipos, 1.024 jugadores, 12 sedes, 96 partidos de la fase de grupos y 437 eventos (365 goles, 72 tarjetas) |
| 2. Qué accesos motivaron la elección | Preguntas que **recorren relaciones**: goleadores (evento → jugador → equipo), sedes del plantel (3 saltos), selecciones conectadas por un estadio compartido, sede más central |
| 3. Modelo | Grafo de propiedades |
| 4. Estructura implementada | Cinco etiquetas (`Equipo`, `Jugador`, `Partido`, `Sede`, `Evento`) y cinco relaciones dirigidas (`PERTENECE_A`, `DISPUTA`, `SE_JUEGA_EN`, `OCURRE_EN`, `PROTAGONIZADO_POR`). Nodos con propiedades mínimas: la ficha completa sigue en MongoDB. El gol es un **nodo** que se recorre, no un campo. |
| 5. Carga y recuperación | `LOAD CSV` + `MERGE` (idempotente), restricciones `IS UNIQUE` por `codigo`. API: `GET /partidos/{codigo}/eventos`. |
| 6. Escalado y distribución | Instancia única. El Hito 1 anticipó que Neo4j no escala bien en escritura masiva: los eventos se escriben de a pocos por partido, y la escritura masiva quedó en Cassandra. Réplicas de lectura en producción [proyección]. |
| 7. Consistencia | Información deportiva, igual que MongoDB: CP (Hito 3). Un gol registrado no puede "desaparecer" de un recorrido. |
| 8. Ante una falla | `/eventos` da 503; fichas, comentarios y estadísticas siguen respondiendo. |
| 9. Trade-off | Duplica identificadores con MongoDB (no fichas); sin transacción entre motores si cambia un plantel. |
| 10. Evidencia | Conteos de nodos y relaciones esperados y obtenidos (`neo4j/docs/evidencia/`). En este hito: sonda HTTP y Bolt, y p95 de `eventos_de_partido`. |

### 2.3 Cassandra — comentarios masivos (Hito 6)

| Pregunta | Respuesta |
| :--- | :--- |
| 1. Qué dato almacena | Comentarios del feed en vivo: 1.100.000 filas cargadas en 96 partidos |
| 2. Qué accesos motivaron la elección | Escritura masiva sostenida (1 M+ por partido, con picos de unas 310 escrituras/s en el partido extremo [diseño]); lectura de "los últimos N comentarios del partido" |
| 3. Modelo | Tabular orientado por consulta (columnar) |
| 4. Estructura implementada | `comentarios_por_partido` con **partición `(partido_id, ventana)`** de 5 minutos y clustering `creado_en DESC, comentario_id`. Tabla duplicada `comentarios_por_usuario` para el historial del usuario. Sin TTL ni DELETE masivo, para evitar tombstones. |
| 5. Carga y recuperación | `COPY` masivo. Una lectura del feed toca **una sola partición**. API: `GET` y `POST /partidos/{codigo}/comentarios`. |
| 6. Escalado y distribución | La ventana convierte una partición ilimitada (unos 162 MiB para el partido extremo) en particiones acotadas (pico de unas 93.000 filas o 15 MiB) [diseño]. Medido: 2.688 particiones, mediana de 215 filas, máximo de 12.087. Umbral de revisión: 100.000 filas o 500 escrituras/s por partición. Si se supera, ventana de 1 minuto o *shard* extra en la clave. `NetworkTopologyStrategy` por región [proyección]. |
| 7. Consistencia | **AP** para el feed (Hito 3). El laboratorio usa `CONSISTENCY ONE` sobre un nodo. Un comentario puede tardar en verse en todas las regiones, o perderse si su única réplica cae antes de copiarse: es tolerable para un feed y no para un dato que no se puede perder. La corrección del Hito 3 agrega que, si no se alcanza el quórum, se acepta la indisponibilidad de escritura. |
| 8. Ante una falla | Prueba B de este hito: con Cassandra detenida, `comentarios` da 503 y las demás rutas siguen igual; la alerta crítica se dispara. Ver el informe de la prueba. |
| 9. Trade-off | Hotspot residual **dentro** de una ventana: el bucket reparte en el tiempo, no en el mismo instante. Sin joins. La idempotencia de los reintentos no sale del modelo (hallazgo del Hito 12). |
| 10. Evidencia | Distribución generada y rendimiento de `COPY` (`cassandra/docs/rendimiento.md`); Hito 12: 0 % de error con 40 a 60 usuarios. En este hito: escrituras por partido, p95 de lectura y escritura, y la prueba B. |

### 2.4 Redis — sesiones y caché (Hitos 7 y 12)

| Pregunta | Respuesta |
| :--- | :--- |
| 1. Qué dato almacena | Sesiones (`sesion:<id>`), copias de fichas (`cache:partido:`, `cache:equipo:`), contadores y votos. Desde el Hito 12, también la caché de la página de comentarios (`cache:comentarios:`). |
| 2. Qué accesos motivaron la elección | Validar una sesión en cada request (menos de 1 ms, Hito 1), 2-3 M de sesiones con vencimiento, y lecturas repetidas de la misma página después de un gol |
| 3. Modelo | Clave/valor en memoria |
| 4. Estructura implementada | Sesión = **Hash** con TTL de 1.800 s renovable (`HSET` + `HINCRBY` atómicos, sin leer-modificar-escribir). Fichas = String JSON con TTL e invalidación al escribir. Caché de comentarios = String JSON con **TTL de 2 s**. `maxmemory 100mb` con `volatile-lru`. |
| 5. Carga y recuperación | `HGETALL` y `GET` por clave conocida; nunca `KEYS *`. API: `GET /sesiones/{id}`, y la caché dentro de `GET /comentarios`. |
| 6. Escalado y distribución | Reparto por usuario (Hito 3). Cada operación toca una sola clave, compatible con Redis Cluster sin *hash tags*. Réplica asincrónica y Sentinel [proyección]. |
| 7. Consistencia | **AP**: se acepta perder sesiones activas (el usuario se vuelve a autenticar, Hito 2). La caché puede mostrar hasta 2 s de atraso frente a Cassandra (Hito 12). |
| 8. Ante una falla | **Prueba A de este hito**: con Redis detenido bajo carga, la caché deja de acertar, las lecturas de comentarios van directo a Cassandra y siguen respondiendo, y las sesiones dan 503. Es un modo degradado, no una caída. |
| 9. Trade-off | Memoria cara y acotada. Con `volatile-lru`, al llenarse se desalojan también sesiones vigentes (riesgo medido en el Hito 7). La caché suma atraso de lectura. |
| 10. Evidencia | Hito 7: TTL, atomicidad bajo concurrencia y presión de memoria. Hito 12: aciertos de 0,98 y lecturas que llegan a Cassandra de 24.469 a 456. En este hito: `redis_up`, memoria, aciertos y la prueba A. |

### 2.5 InfluxDB — estadísticas en vivo (Hito 8)

| Pregunta | Respuesta |
| :--- | :--- |
| 1. Qué dato almacena | Estadísticas por equipo (posesión, pases, tiros), por jugador (velocidad, distancia), actividad de usuarios por región y métricas de plataforma |
| 2. Qué accesos motivaron la elección | "Últimos 5 minutos del partido", "comparar los dos equipos", "posesión promedio por ventana": rangos de tiempo y agregación. Hito 1: 10 M+ puntos por partido. |
| 3. Modelo | Series temporales (multidimensional). Puntaje 3,90 contra 3,45 de Cassandra en el Hito 2. |
| 4. Estructura implementada | Cuatro tablas. **Tags** solo para lo que se filtra (`partido_id`, `equipo_id`, `sede`, `grupo`, `region`); `jugador_id` es tag únicamente en `estadisticas_jugador`, la tabla cuyo patrón lo filtra, para no multiplicar series en las demás. Precisión: segundos. La agregación correcta depende del significado de cada medida (AVG para muestras, MAX para contadores acumulados, SUM para conteos por intervalo). |
| 5. Carga y recuperación | Line protocol por lotes. **10.598.400 puntos cargados** [medido]. Consultas SQL con `date_bin`. API: `GET /partidos/{codigo}/estadisticas` con ventana máxima de 3 horas. |
| 6. Escalado y distribución | Base `fixture2030_vivo` con precisión original y retención acotada; `fixture2030_hist` con resumen de 1 minuto sin expiración (unas 30 veces menos puntos). Para crecer: más nodos de ingesta [proyección]. |
| 7. Consistencia | **AP** (Hito 3): la ingesta no se detiene y acepta datos tardíos o desordenados. Leer la evolución en el tiempo tolera convergencia eventual. |
| 8. Ante una falla | `/estadisticas` da 503; el feed, las fichas y las sesiones siguen. En producción, buffer de ingesta [proyección]. |
| 9. Trade-off | No es una base de propósito general; el período de retención se fija al crear la base. |
| 10. Evidencia | Corrida completa de 10.598.400 puntos y validaciones (`influxdb/docs/evidencia/`). En este hito: `/metrics` nativo y p95 de `estadisticas`. |

### 2.6 IRIS — el partido como entidad compleja (Hito 9)

| Pregunta | Respuesta |
| :--- | :--- |
| 1. Qué dato almacena | Partido con su estado, sus eventos, su terna arbitral y su sede; personas (jugador, árbitro, técnico) con herencia |
| 2. Qué accesos motivaron la elección | El partido necesita **reglas junto al dato**: no se finaliza un partido que no empezó, un evento no existe sin su partido, el marcador coincide con los goles. Ninguno de los modelos anteriores guarda reglas. |
| 3. Modelo | Objetos persistentes |
| 4. Estructura implementada | `Partido` persistente con estado (`Programado → EnJuego → Finalizado`) como propiedad con transiciones. `Evento` y `Designacion` como hijos (padre-hijo). `Direccion` como objeto serial embebido en `Sede`. `Persona` con herencia en `Jugador`, `Arbitro` y `Tecnico`. Las invariantes se aplican en `%OnBeforeSave`: un evento exige partido `EnJuego`. |
| 5. Carga y recuperación | Clases `.cls` compiladas; carga desde CSV; acceso por objeto y por SQL. API: `GET /partidos/{codigo}/detalle`. |
| 6. Escalado y distribución | Instancia única. Mirroring o servidores de aplicación (ECP) [proyección]. Es el módulo de menor volumen y mayor riqueza de reglas. |
| 7. Consistencia | Fuerte dentro del objeto: la regla se aplica en cada guardado, sin importar qué aplicación escriba. |
| 8. Ante una falla | `/detalle` da 503; el resto sigue funcionando. |
| 9. Trade-off | Producto propietario (edición Community en el laboratorio) y otro lenguaje (ObjectScript); suma un sexto motor al costo operativo. |
| 10. Evidencia | Matriz de integridad: cada operación ilegal rechazada con su motivo (`iris/docs/matriz_de_integridad.md`). En este hito: `/api/monitor/metrics` y p95 de `detalle_partido`. |

## 3. Preguntas transversales (sección 6.4)

### ¿Por qué no tratar todos los datos con una única estructura?

Porque cada estructura hace barata una operación y cara otra:
- La partición por `(partido, ventana)` que vuelve barato escribir un millón de comentarios haría carísimo recorrer gol → jugador → equipo.
- El grafo que vuelve natural ese recorrido no está pensado para ingerir 10 M de puntos por partido ni para expirar sesiones por TTL.
- Un documento con reglas en la aplicación no aplica la invariante "no hay eventos en un partido no iniciado" si otra aplicación escribe directo; un objeto persistente sí.

La comparación con una alternativa relacional del Hito 12 (`carga-optimizacion/docs/comparacion_relacional.md`) muestra lo mismo desde el otro lado. SQL simplifica la idempotencia, la integridad referencial y los joins, pero concentra las escrituras de un partido en el mismo extremo de un índice, y escala sobre todo verticalmente.

### ¿Cómo se relacionan los módulos sin forzar una única base?

- **Identificadores compartidos** definidos en el Hito 4: código FIFA (`ARG`), código de jugador (`ARG-10-xxxxxx`) y de partido (`F2030-NNN`). Todas las bases los usan, y ninguna copia la ficha de otra.
- **Una API con un adaptador por base** (Hito 10). Cada ruta declara qué base la atiende; ninguna mezcla modelos; los errores se traducen igual en todas (503 = base no disponible; 404 = no existe).
- **Cruces analíticos fuera de las bases operacionales**: el Data Mart del Hito 12.

No hay transacciones entre motores. Si cambia un plantel, Mongo y Neo4j se actualizan por separado: es un riesgo aceptado y declarado desde el Hito 4.

### ¿Qué datos son operacionales y cuáles se proyectan a una vista analítica?

**Operacionales:** los de las seis bases, es decir, lo que la API sirve en el momento.

**Analíticos:**
- el **Data Mart** del Hito 12, que responde "¿cuánto aumentan los comentarios en los 5 minutos posteriores a un gol?" cruzando Cassandra, Neo4j y MongoDB con un ETL incremental cada 5 minutos;
- el **resumen de 1 minuto** de InfluxDB (`fixture2030_hist`).

Ninguna consulta analítica recorre las particiones operacionales en vivo.

### ¿Dónde se usa caché y cómo se invalida o expira?

| Caché | Dónde | Expiración | Invalidación |
| :--- | :--- | :--- | :--- |
| Sesión | Redis Hash | TTL 1.800 s, renovado en cada acción | Cierre explícito (`DEL`) o suspensión por `estado` |
| Fichas de partido y de equipo | Redis String | TTL de 300 s y 3.600 s | `DEL` al escribir en la fuente de verdad (Hito 7) |
| Página de comentarios (ventana actual) | Redis String | **TTL de 2 s** | Sin invalidación: expira sola. Se acepta hasta 2 s de atraso. |

### ¿Cómo se evita que una consulta de alto volumen bloquee todo el sistema?

- **Cada lectura toca una partición conocida:** Cassandra lee una partición `(partido, ventana)` e InfluxDB acota la ventana a un máximo de 3 horas. No hay `ALLOW FILTERING` ni `KEYS *`.
- **Límites en la API:** `limit` con tope de 100 (`MAX_LIMIT`) y **timeout de 3 s por dependencia**. Una base lenta devuelve 503 en esa ruta en vez de retener hilos indefinidamente.
- **Corte rápido por base** (agregado en este hito, a partir de la evidencia): después de una falla de conexión, la API deja de intentar esa base por 10 s. Responde 503 al instante, o lee sin caché si la que cayó es Redis, en vez de pagar en cada request los 2,4 s que tarda en fallar una conexión en Windows. Ver [`limitaciones_y_evidencia.md`](limitaciones_y_evidencia.md).
- **Caché delante de la partición caliente** (Hito 12): el 98 % de las lecturas del pico no llega a Cassandra.
- **Aislamiento entre bases:** se comprobó en este hito (pruebas A y B). Con Cassandra detenida, solo comentarios dio 503 y Mongo, Neo4j e IRIS siguieron en 200. Con Redis detenido bajo carga, la API sostuvo 88,5 de 92,1 requests/s.

### ¿Qué parte de la escalabilidad fue medida y qué parte es proyección?

| Medido | Proyección (no existe en el laboratorio) |
| :--- | :--- |
| 10.598.400 puntos cargados en InfluxDB (Hito 8) | 2-3 M de usuarios simultáneos y 100.000+ requests/s (objetivos del TPO) |
| 1.100.000 comentarios en 96 partidos; distribución por partición (Hito 6) | Réplicas y consistencia entre regiones (Hito 3) |
| Prueba de carga con 40 a 60 usuarios: p95 de la API de 16 a 26 ms y 0 % de errores, con caché de 0,98 de aciertos (Hito 12) | Comportamiento del clúster ante la caída de un nodo o de una región |
| Este hito, con 20 usuarios: 91,6 requests/s, p95 de 24 ms y 0 % de errores; una base caída degrada una sola función; detección en 10-15 s y alerta crítica en 85-90 s | 99,99 % de disponibilidad anual |

### ¿Cómo se interpretan las métricas de Prometheus y Grafana?

Ver [`metricas_y_consultas.md`](metricas_y_consultas.md) (qué mide cada consulta, unidad y ventana) y [`../grafana/README.md`](../grafana/README.md) (qué pregunta responde cada panel). El orden de lectura ante un problema es:
1. salud por base;
2. errores;
3. latencia de la API;
4. latencia por base;
5. caché.

### ¿Qué decisión se toma si una base queda temporalmente indisponible?

| Base caída | Qué sigue funcionando | Modo degradado | Decisión |
| :--- | :--- | :--- | :--- |
| MongoDB | Comentarios, eventos, estadísticas, sesiones | Sin fichas de equipo ni de jugador (la caché de fichas del Hito 7 no está conectada a la API: sería la siguiente mejora) | Reiniciar el nodo; en producción, elección de un nuevo primario |
| Neo4j | Todo menos los recorridos | Sin eventos ni goleadores | Reiniciar; en producción, servir desde réplicas de lectura |
| Cassandra | Fichas, eventos, estadísticas, sesiones, detalle | **Sin feed de comentarios** (alerta crítica). La página en caché se sirve hasta 2 s. | Prioridad máxima en partido en vivo; en producción, las otras réplicas siguen (AP) |
| Redis | Todo, con más latencia en comentarios | **Sin sesiones** (reautenticar) y **sin caché**: las lecturas pasan a Cassandra | Vigilar la carga de Cassandra; reiniciar Redis. La pérdida de sesiones está aceptada. |
| InfluxDB | Todo menos estadísticas | Sin estadísticas en vivo | Buffer de ingesta en producción para no perder puntos |
| IRIS | Todo menos el detalle del partido | Sin detalle ni validación de reglas | Reiniciar; las escrituras de estado esperan |

## 4. Costo operativo de mantener seis modelos

| Costo | Cómo se ve en este repositorio | Mitigación aplicada |
| :--- | :--- | :--- |
| Seis motores para instalar, actualizar y respaldar | Seis `docker-compose`, seis drivers en la API, seis convenciones de persistencia; en Windows, desvíos como el volumen de Docker para IRIS, los puertos alternativos cuando Windows reserva el 52773 y la contraseña obligatoria de `_SYSTEM` | Un compose por módulo y `iniciar_monitoreo --con-bases` para levantarlos igual |
| Seis formas de monitorear | Exporters para Redis y MongoDB, endpoints nativos para InfluxDB (con token) e IRIS. Neo4j Community y Cassandra **sin** métricas internas: solo sondas y la vista de la API. | Una API instrumentada que mide a las seis con las mismas métricas (`fixture_dependencia_*`) |
| Seis modelos de consistencia | CP para información deportiva, AP para comentarios, sesiones y estadísticas | Decidido por dato en el Hito 3 y documentado por módulo |
| Sin transacciones entre motores | Un cambio de plantel toca Mongo y Neo4j por separado | Identificadores compartidos y verificación de huérfanos |
| Conocimiento del equipo | MQL, Cypher, CQL, comandos de Redis, SQL de InfluxDB y ObjectScript | Documentación por módulo y API única para las aplicaciones |

El Hito 1 ya lo había advertido al dejar equipos, jugadores y partidos en NoSQL: un motor relacional adicional *"implica más infraestructura para instalar, mantener y monitorear"*. Por eso la decisión no es "más motores es mejor", sino **un motor solo cuando su patrón de acceso lo justifica**.
