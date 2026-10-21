# Pruebas, evidencia y coherencia con el TPO — Hito 10

**Grupo N.º 8** · Fixture 2030

## 1. Qué se prueba

La entrega incluye pruebas reproducibles en dos niveles (RF15):

### Tests automáticos (`tests/`, sin bases levantadas)
Verifican el contrato y el manejo de errores sin depender de ninguna fuente, por
lo que corren en cualquier máquina con `pytest tests/`:

| Prueba | Qué demuestra | Requisito |
| :--- | :--- | :--- |
| `test_openapi_lista_las_rutas` | OpenAPI declara las rutas implementadas | RF13, RNF2 |
| `test_salud_responde_200_con_dependencias` | `/salud` informa las 6 fuentes | RF17 |
| `test_request_id_vuelve_en_header` | Correlación por `X-Request-ID` | RF18 |
| `test_validacion_limit_invalido_no_consulta_la_base` | Validación antes de consultar | RNF3 |
| `test_validacion_fechas_invertidas_en_estadisticas` | Rango temporal validado | RNF3 |
| `test_formato_de_error_es_consistente` | Estructura de error común | RNF4 |
| `test_dependencia_caida_devuelve_503_no_200` | Dependencia caída → 503, sin fuga técnica | RF11, RF12, RNF9 |
| `test_ventana_cassandra_trunca_a_5_minutos` | La API respeta la partición del Hito 6 | RNF13 |
| `test_sesion_inexistente_sin_redis_es_dependencia` | Distinción ausencia vs. caída | RF6 |

### Pruebas manuales (Postman / Swagger, con bases levantadas)
La colección `postman/fixture2030_collection.json` cubre, por fuente: una request
válida, un parámetro inválido, un recurso inexistente y la escritura de comentario.
Se puede correr desde Postman, con Newman, o reproducir con los `curl` del README.

## 2. Escenarios de error exigidos por la consigna

| Escenario | Cómo se prueba | Resultado |
| :--- | :--- | :--- |
| Operación exitosa | `GET /equipos/ARG` con Mongo arriba | 200 + documento |
| Entrada inválida | `?limit=0` o fechas invertidas | 400 `VALIDATION_ERROR` |
| Recurso inexistente | `GET /equipos/ZZZ` | 404 `TEAM_NOT_FOUND` |
| Respuesta vacía válida | comentarios de una ventana sin datos | 200 + lista vacía |
| Sesión ausente/expirada | `GET /sesiones/no-existe` con Redis arriba | 404 `SESSION_EXPIRED_OR_NOT_FOUND` |
| Dependencia detenida | apagar una base y repetir su endpoint | 503 `DEPENDENCY_UNAVAILABLE` |
| Escritura repetida | `POST` comentario reusando `comentarioId` | no duplica (upsert) |

## 3. Evidencia

La evidencia de cada corrida va en `docs/evidencia/` (logs de la API y/o capturas
de Swagger y Postman), **sin secretos** (RNF7). El procedimiento para generarla
está en `docs/evidencia/README.md`. Como esta API se prueba contra las bases en
la notebook, la evidencia la produce el equipo en su entorno.

### 3.1 Capturas de esta corrida (Swagger UI)

Se probó con cuatro fuentes levantadas (MongoDB, Neo4j, Cassandra, Redis) y las
otras dos detenidas (InfluxDB, IRIS), para cubrir todos los escenarios exigidos.
`/salud` en esta corrida reportó: mongodb, neo4j, cassandra y redis en `true`;
influxdb e iris en `false`.

| Fuente | Escenario | Resultado | Captura |
| :--- | :--- | :--- | :--- |
| MongoDB | Equipo existente | 200 | `mongo_equipo_ok.jpg` |
| MongoDB | Equipo inexistente | 404 `TEAM_NOT_FOUND` | `mongo_equipo_inexistente.jpg` |
| MongoDB | Base detenida | 503 | `mongo_dependencia_caida.jpg` |
| Neo4j | Eventos de partido | 200 | `neo4j_eventos_ok.jpg` |
| Neo4j | Partido inexistente | 404 | `neo4j_partido_inexistente.jpg` |
| Redis | Sesión vigente | 200 | `redis_sesion_ok.jpg` |
| Redis | Sesión ausente/expirada | 404 `SESSION_EXPIRED_OR_NOT_FOUND` | `redis_sesion_inexistente.jpg` |
| Cassandra | Alta de comentario | 201 | `cassandra_comentario_creado.jpg` |
| Cassandra | Lectura de la ventana | 200 | `cassandra_comentarios_lectura.jpg` |
| Cassandra | Instante inválido | 400 `VALIDATION_ERROR` | `cassandra_instante_invalido.jpg` |
| InfluxDB | Base detenida | 503 `DEPENDENCY_UNAVAILABLE` | `influx_dependencia_caida.jpg` |
| IRIS | Base detenida | 503 `DEPENDENCY_UNAVAILABLE` | `iris_dependencia_caida.jpg` |

> Los nombres de arriba son la convención sugerida; renombrar las capturas reales
> para que coincidan. Si alguna captura de Mongo/Neo4j/Redis quedó con otro
> nombre, ajustarlo o actualizar esta tabla.

El *happy-path* de InfluxDB e IRIS no se incluye en esta corrida porque esos dos
módulos no estaban inicializados en la notebook (InfluxDB requiere el token del
Hito 8; IRIS, su driver propio). Se prueban levantando cada módulo por separado,
según el esquema de tandas de `docs/conectividad_y_configuracion.md` §5. Su `503`
demuestra que el endpoint y el adaptador están cableados y que el manejo de
dependencia caída funciona (RF11, RF12, RNF9): la API no oculta la falla con un
200 ni filtra detalle técnico.

## 4. Rendimiento básico (RNF18)

No se declaran cifras de latencia sin método. Si se miden, deben indicar: entorno
(notebook, API local), volumen de datos, configuración (timeout, límites) y
limitaciones. A nivel diseño, cada endpoint ejecuta **una** operación acotada por
clave/partición/rango; no hay recorridos ni escaneos sin criterio (RNF13).

## 5. Coherencia con el TPO

| Hito | Módulo | Cómo lo usa la API |
| :--- | :--- | :--- |
| 4 | MongoDB (equipos/jugadores) | Endpoints de equipo y plantel, respetando índices y proyección |
| 5 | Neo4j (partidos/eventos) | Endpoint de eventos con Cypher parametrizado |
| 6 | Cassandra (comentarios) | Lectura/escritura respetando la partición `(partido_id, ventana)` |
| 7 | Redis (sesiones) | Lectura de sesión con distinción ausente/caído |
| 8 | InfluxDB (series) | Estadísticas por ventana temporal con validación de rango |
| 9 | IRIS (entidad compleja) | Detalle del partido desde la proyección SQL |

La API es una **capa de integración controlada**: encapsula las diferencias de
cada motor detrás de contratos HTTP, sin convertir todas las bases en una sola
estructura ni exponer consultas arbitrarias. Cada decisión de los hitos previos
(partición por ventana, referencias en Mongo, TTL de Redis, postura CP/AP) se
preserva: la API no la reemplaza, la expone.

## 6. Límites del laboratorio

- No demuestra escala (millones de usuarios): se prueba en una notebook con datos de laboratorio.
- No implementa autenticación real ni rate limiting; documenta dónde irían.
- La evidencia de los endpoints depende de que la fuente correspondiente esté levantada.
