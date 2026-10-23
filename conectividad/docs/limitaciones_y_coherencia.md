# Limitaciones y coherencia con el TPO

**Grupo 8** · Fixture 2030 · Hito 11 (secciones 6 y 8)

## 1. Limitaciones

### Del entorno

- **Una sola notebook.** Las seis bases, la API y la evaluación corren en la misma máquina
  (Windows 11, 32 GB, Docker Desktop con WSL2). Las latencias son de loopback: sirven para
  comparar capas y detectar demoras anómalas (H4), **no** para estimar tiempos en red ni capacidad.
- **Sin red de Compose común.** Cada producto vive en su propia red. La API en contenedor no se
  probó; está documentado qué cambiaría ([`topologia_y_entornos.md`](topologia_y_entornos.md) §4).
- **Proxy de puertos de Docker Desktop.** Con un contenedor detenido, su puerto publicado sigue
  aceptando TCP. En Linux nativo (sin Docker Desktop) el mismo caso daría *connection refused*.
- **Comportamiento de Windows ante el rechazo:** un `connection refused` tarda ~2 s por familia de
  direcciones (reintentos del SYN), por eso 4 s para `localhost:27018`. En Linux es inmediato.

### De los datos

- **Datos de laboratorio del equipo**, cargados con los scripts de cada hito: Hito 4 (64 equipos,
  1.024 jugadores), Hito 5 (96 partidos, 437 eventos), Hito 6 (muestra de 13 comentarios en dos
  tablas), Hito 7 (muestra: 200 sesiones, 344 claves), Hito 8 (perfil `muestra`: 22.080 puntos,
  más los datos de una versión anterior que ya había en la notebook) e Hito 9 (carga completa).
- **Las sesiones de Redis vencen a los 1.800 s.** Si pasa media hora desde la carga, la prueba de
  `sesion:S0001` da “no existe (TTL=-2)” y la ruta `/sesiones/S0001`, 404. No es una falla de
  conectividad: hay que repetir la carga de muestra del Hito 7 (README, preparación).
- **InfluxDB tiene dos esquemas en la misma tabla** (los puntos viejos sin `pases_acum` y los de la
  muestra actual). La ventana de prueba apunta a los puntos nuevos.

### De las pruebas

- **No se modificó la API del Hito 10.** H1, H2, H6, H7 y H8 quedan diagnosticados, con evidencia
  y con el cambio propuesto, pero **no corregidos**: sus rutas siguen fuera de contrato.
- **No se probó el `POST /partidos/{codigo}/comentarios`**: escribe en Cassandra y RNF6 pide
  operaciones no destructivas. Su conectividad queda cubierta por las mismas capas que el `GET`.
- **No se probaron credenciales inválidas contra Cassandra ni Redis**: en el laboratorio no tienen
  autenticación (se demostró con el frame `STARTUP → READY` y con `AUTH`, que responde que no hay
  password configurada).
- **El escenario de timeout bajo no es determinístico** en loopback (§3 de
  [`diagnostico_de_fallas.md`](diagnostico_de_fallas.md)).
- **Un solo intento de credencial inválida en Neo4j**, para no disparar el bloqueo por intentos fallidos.
- **Las capturas son texto.** La evidencia son salidas de consola, JSON y logs redactados, no
  imágenes (ver [`evidencia/capturas_redactadas/`](evidencia/capturas_redactadas/)).
- **Conectividad no es rendimiento.** Nada de este hito permite concluir cuántas operaciones por
  segundo soporta la API: eso es el Hito 12.

### Herramientas

- No hay clientes nativos instalados en la notebook (`mongosh`, `cqlsh`, `redis-cli`, …). Por eso
  se ejecutan dentro de cada contenedor con `docker exec` (origen = contenedor). Si Docker no está
  disponible, esas pruebas quedan en **SKIP**, no en falla.
- Los drivers son los de la API (`api/.venv`, Python 3.11). Con otro Python sin esos paquetes,
  las pruebas de driver quedan en SKIP. Con Python 3.12+, `cassandra-driver` no carga (el adaptador
  de la API cae a `cqlsh`), y la evaluación lo informa como SKIP del driver.

## 2. Coherencia con el TPO

| Hito | Módulo | Qué aporta a este hito | Qué encontró este hito |
| :--- | :--- | :--- | :--- |
| 1–3 | Análisis, modelo conceptual, postura CAP | Elección de un motor por necesidad (documental, grafo, tabular, clave/valor, series, objetos) | Cada motor necesita **su** prueba de protocolo y de contexto: no hay un health genérico (RNF4) |
| 4 | MongoDB (equipos/jugadores) | Credencial de laboratorio, database `fixture2030`, `codigo` como identificador de negocio | H1: la API supone `_id = codigo` |
| 5 | Neo4j (grafo de partidos) | Bolt + Browser, Cypher parametrizado, `F2030-*` | Disponible de punta a punta; partido inexistente ≠ partido sin eventos |
| 6 | Cassandra (comentarios) | Clave `(partido_id, ventana)`, sin `ALLOW FILTERING` | Disponible; consulta inválida ≠ timeout de conexión |
| 7 | Redis (sesiones) | Sesión como **hash** con TTL de 1.800 s, persistencia AOF/RDB | H2: la API lee con `GET`; la falla controlada confirmó la persistencia (344 → 344 claves) |
| 8 | InfluxDB (series) | Token local fuera de Git, `fixture2030_vivo`, `pases_acum` | C0 (token), H5 (esquema anterior), H6 (`query` vs `q`), H4 (IPv4) |
| 9 | IRIS (objetos) | Proyección SQL `Fixture.*`, namespace `USER` | H3 (password expirada), H7 (alias reservado `local`) |
| 10 | API integrada | Adaptadores, error común, request-id, `/salud`, `DEP_TIMEOUT_S` | Fallas rápidas y aisladas por ruta (bien), pero 503 para todo y `/salud` sin causa (RF18) |
| 11 | **Este hito** | Procedimiento por capas, matriz, fallas controladas | Base confiable para el Hito 12: qué entorno, host, puerto, cliente y contexto usa la API, y qué rutas hoy no sirven para medir carga |
| 12 | Pruebas de carga | — | **No medir carga sobre rutas fuera de contrato** (Mongo, Redis, InfluxDB, IRIS) hasta corregir H1, H2, H6 y H7: se mediría la velocidad de un error. Usar `127.0.0.1` (H4) y calentar las conexiones antes de medir (Cassandra ~1,6 s en frío) |
