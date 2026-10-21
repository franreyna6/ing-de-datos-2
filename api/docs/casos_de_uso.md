# Casos de uso — API integrada (Hito 10)

**Grupo N.º 8** · Fixture 2030

Cada endpoint resuelve un caso de uso concreto del Fixture y atiende una fuente
justificada por su modelo. No hay un endpoint genérico que reciba el nombre de
una base, una colección y una consulta libre (restricción de la consigna).

## Mapa de endpoints

| Método | Ruta | Fuente | Operación | Caso de uso |
| :--- | :--- | :--- | :--- | :--- |
| GET | `/equipos/{codigo}` | MongoDB | lectura | Ficha de un equipo por su código |
| GET | `/equipos/{codigo}/jugadores` | MongoDB | lectura | Plantel paginado de un equipo |
| GET | `/partidos/{codigo}/eventos` | Neo4j | lectura | Eventos conectados a un partido |
| GET | `/partidos/{codigo}/comentarios` | Cassandra | lectura | Feed de comentarios de una ventana |
| POST | `/partidos/{codigo}/comentarios` | Cassandra | escritura | Publicar un comentario |
| GET | `/sesiones/{sesion_id}` | Redis | lectura | Verificar si una sesión está vigente |
| GET | `/partidos/{codigo}/estadisticas` | InfluxDB | lectura | Estadísticas en una ventana temporal |
| GET | `/partidos/{codigo}/detalle` | IRIS | lectura | Detalle del partido como entidad compleja |
| GET | `/salud` | todas | lectura | Disponibilidad de la API y de cada fuente |

## Detalle por caso de uso

### 1. Ficha de equipo (MongoDB)
- **Consume:** la aplicación cliente / Swagger / Postman.
- **Entrada:** `codigo` del equipo (p. ej. `ARG`).
- **Respuesta:** documento proyectado (código, nombre, confederación, ranking, grupo, sede).
- **Si no existe:** `404 TEAM_NOT_FOUND`.
- **Si Mongo no responde:** `503 DEPENDENCY_UNAVAILABLE`.
- **Éxito:** se devuelve el equipo pedido con 200.

### 2. Plantel de un equipo (MongoDB)
- **Entrada:** `codigo` + opcional `posicion`, `limit` (máx. 100), `offset`.
- **Respuesta:** lista paginada de jugadores.
- **Validación previa:** `limit >= 1`, `offset >= 0` (si no, `400` sin consultar).
- **Patrón de acceso:** filtro por `equipoCodigo`, que es el índice del Hito 4.

### 3. Eventos de un partido (Neo4j)
- **Entrada:** `codigo` del partido + `limit`.
- **Respuesta:** eventos (gol/tarjeta) con su minuto y jugador, vía recorrido de grafo.
- **Partido inexistente vs. sin eventos:** el primero es `404 MATCH_NOT_FOUND`; el segundo devuelve lista vacía con 200.

### 4. Comentarios de un partido (Cassandra)
- **Entrada:** `codigo` + opcional `instante` (ISO-8601) + `limit`.
- **Respuesta:** una página de comentarios de **una ventana de 5 minutos** (una partición).
- **Por qué `instante`:** la aplicación deriva la ventana (bucket de 5 min) y lee una sola partición, respetando la clave `(partido_id, ventana)` del Hito 6. Si se omite, se usa la hora actual.
- **Éxito:** se devuelven los comentarios de esa ventana (puede ser lista vacía válida).

### 5. Publicar comentario (Cassandra, escritura)
- **Entrada:** cuerpo JSON `{usuarioId, contenido, comentarioId?}`.
- **Respuesta:** `201` con el `comentarioId` y la `ventana` asignados.
- **Idempotencia:** si el cliente envía `comentarioId` (clave de idempotencia), reintentar reescribe la misma fila en vez de duplicar. Sin ese id, cada POST crea un comentario nuevo. Ver `contratos_y_errores.md`.

### 6. Estado de sesión (Redis)
- **Entrada:** `sesion_id`.
- **Respuesta:** estado de la sesión y TTL restante.
- **Distinción clave:** sesión activa → `200`; ausente o expirada → `404 SESSION_EXPIRED_OR_NOT_FOUND`; Redis caído → `503`. Nunca se confunde una ausencia con una caída.

### 7. Estadísticas temporales (InfluxDB)
- **Entrada:** `codigo` + `desde` + `hasta` (ISO-8601).
- **Validación previa:** formato de fechas, `desde < hasta` y ventana ≤ 3 horas (para no traer un volumen ilimitado).
- **Respuesta:** puntos de `estadisticas_equipo` en `[desde, hasta)`.

### 8. Detalle de partido (IRIS)
- **Entrada:** `codigo`.
- **Respuesta:** DTO de la entidad compleja (estado, goles, local/visitante, sede, cantidad de eventos).
- **Alcance:** solo lectura. Cambiar el estado exigiría invocar las transiciones de dominio del Hito 9 (`Iniciar`/`Finalizar`), que quedan fuera de este hito.
