# Contratos, validación y errores — API integrada (Hito 10)

**Grupo N.º 8** · Fixture 2030

## 1. Contrato OpenAPI

El contrato vive en `openapi/openapi.yaml` y se **genera desde la propia app**
(FastAPI), por lo que coincide con el comportamiento real (RNF2). Se explora en
Swagger UI: `http://localhost:8000/docs`. El JSON equivalente está en
`http://localhost:8000/openapi.json`.

Documenta, como mínimo: título y versión, servidor local, tags por recurso,
rutas y métodos, parámetros de ruta y query, cuerpos de request, schemas de
respuesta, códigos HTTP posibles y el esquema de error.

## 2. Formato de error común

Toda respuesta de error tiene la misma forma (RNF4), sin stack traces, consultas
internas ni credenciales (RF12):

```json
{
  "error": {
    "code": "TEAM_NOT_FOUND",
    "message": "No existe el equipo 'ZZZ'.",
    "request_id": "a1b2c3d4",
    "detalles": { "recurso": "ZZZ" }
  }
}
```

El `request_id` también viaja en el header `X-Request-ID` y aparece en los logs,
de modo que una respuesta se puede correlacionar con su traza (RF18).

## 3. Situaciones y códigos

| Situación | HTTP | `code` | Quién lo detecta |
| :--- | :--- | :--- | :--- |
| Parámetro/cuerpo inválido | 400 | `VALIDATION_ERROR` | Schema (Pydantic) o servicio, antes de consultar |
| Recurso inexistente | 404 | `*_NOT_FOUND` / `SESSION_EXPIRED_OR_NOT_FOUND` | Servicio (adaptador devolvió vacío) |
| Conflicto de estado | 409 | `CONFLICT` | Servicio (reservado para escrituras con regla de estado) |
| Dependencia no disponible | 503 | `DEPENDENCY_UNAVAILABLE` | Adaptador (fallo/timeout del driver) |
| Error inesperado | 500 | `INTERNAL_ERROR` | Manejador global; detalle solo en logs |

La regla de oro de la Clase 11: **nunca se devuelve 200 para esconder una falla
de conexión**. Una lista vacía es válida solo cuando la base respondió y no había
datos; si la base no respondió, es 503.

## 4. Validación antes de consultar (RNF3)

La validación ocurre en el borde, antes de abrir una operación contra la base:

- Tipos y rangos de `limit`/`offset` (vía Query de FastAPI y tope `MAX_LIMIT`).
- Fechas ISO-8601 de InfluxDB: formato, `desde < hasta` y ventana ≤ 3 h.
- Cuerpo de comentario: `usuarioId` y `contenido` no vacíos, longitudes máximas.

Un parámetro incorrecto no produce una consulta costosa ni ambigua contra la fuente.

## 5. Idempotencia de las escrituras (RF19, RNF14)

| Operación | ¿Repetible sin efecto? | Comportamiento ante reintento |
| :--- | :--- | :--- |
| Todos los `GET` | Sí | No producen cambios |
| `POST /partidos/{codigo}/comentarios` | Depende | Con `comentarioId` (clave de idempotencia): reinsertar el mismo id reescribe la misma fila (upsert de Cassandra), no duplica. Sin ese id: cada reintento crea un comentario nuevo |

Por eso el contrato ofrece `comentarioId` opcional: un cliente que reintenta por
una respuesta perdida puede reusar el mismo id y evitar duplicados.

## 6. Timeouts y dependencias caídas (RNF8, RNF9)

Cada adaptador configura un timeout (`DEP_TIMEOUT_S`, por defecto 3 s) en la
conexión y las operaciones. Si una base tarda más o no responde, el adaptador
corta y traduce a 503 con `request_id`, sin dejar la request colgada ni filtrar
información técnica.

## 7. Seguridad del contrato (RF12, RNF7)

- No se publican URIs con credenciales, tokens ni passwords en OpenAPI, Postman, código ni logs.
- Los mensajes de error son de dominio; la causa técnica (excepción del driver) va solo al log.
- Postman usa variables (`baseUrl`, `partidoCodigo`, …) sin secretos.
