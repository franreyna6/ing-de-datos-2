# Arquitectura y adaptadores — API integrada (Hito 10)

**Grupo N.º 8** · Fixture 2030 · FastAPI

## 1. Capas

La aplicación separa el contrato HTTP de la forma en que cada producto realiza la
operación (RNF1). El flujo de una request es el de la Clase 11:

```
Cliente HTTP (Swagger / Postman / cURL)
      │
      ▼
Router / ruta        app/routes/      valida tipos, describe el contrato OpenAPI
      │
      ▼
Servicio             app/services/    reglas del caso de uso y validación de negocio
      │
      ▼
Adaptador            app/adapters/    ÚNICO lugar que conoce el driver de cada base
      │
      ▼
Driver / cliente nativo → Base NoSQL
```

Reglas que sostienen la separación:

- **Las rutas no tocan drivers.** Reciben parámetros validados, llaman al servicio y devuelven. No arman consultas ni deciden conexiones.
- **Los servicios no conocen HTTP.** No saben de códigos de estado; lanzan excepciones de dominio (`ErrorNoEncontrado`, `ErrorValidacion`, `ErrorDependencia`).
- **El código HTTP se decide en un solo lugar:** el manejador central de `app/main.py` traduce cada excepción de dominio a su status. Así un adaptador describe *qué pasó*, no *qué código HTTP* corresponde.

## 2. Qué encapsula cada adaptador

Todos siguen el mismo molde (RNF5), con el driver importado de forma **perezosa**
para que la API arranque aunque una base no esté instalada o levantada:

| Responsabilidad | Cómo se cumple |
| :--- | :--- |
| Crear/recibir la conexión | Conexión perezosa y reutilizada por proceso, con timeout (RNF8) |
| Seleccionar database/keyspace/namespace | Desde la configuración por entorno (nunca hardcode) |
| Ejecutar la operación | Consulta fija y parametrizada, acotada con límite/paginación |
| Transformar errores del cliente | Cualquier fallo del driver → `ErrorDependencia` (503) |
| Convertir la respuesta al modelo interno | DTO estable; no se exponen `_id`, campos internos ni la instancia entera |
| Administrar recursos | Método `cerrar()` y `verificar()` para el health-check |

## 3. Particularidades que cada adaptador respeta

No se borran las diferencias entre modelos; se encapsulan (nota de la Clase 11):

- **MongoDB:** consulta documental por `_id` (código de negocio) y filtro por `equipoCodigo`, con proyección. Mapea `_id → codigo` para no exponer el identificador interno.
- **Neo4j:** Cypher **fijo y parametrizado** (`$codigo`); jamás concatena texto del cliente ni acepta Cypher externo. Distingue partido inexistente de partido sin eventos.
- **Cassandra:** respeta la clave de partición `(partido_id, ventana)` del Hito 6. Deriva la ventana de 5 minutos del instante recibido y lee **una** partición con `LIMIT`. Usa *prepared statements*. Nunca `ALLOW FILTERING`.
- **Redis:** separa clave ausente/expirada (404) de Redis no disponible (503). Expone solo los campos útiles de la sesión, no el valor interno completo.
- **InfluxDB:** SQL fijo parametrizado por partido y rango `[desde, hasta)`; valida el intervalo antes de consultar; acota la ventana. El token se lee del entorno.
- **IRIS:** lee la proyección SQL de las clases persistentes del Hito 9 por código; arma un DTO y no serializa la instancia completa. No ejecuta transiciones de estado (solo lectura).

## 4. Núcleo transversal (`app/core/`)

| Archivo | Rol |
| :--- | :--- |
| `config.py` | Toda la configuración por variables de entorno (RF16, RNF6) |
| `errores.py` | Excepciones de dominio y formato de error común (RF11, RF12) |
| `registro.py` | Logging con request-id para correlación (RF18, RNF10) |

## 5. Tolerancia a fallas

Como cada driver se importa de forma perezosa y cada adaptador traduce sus fallos
a `ErrorDependencia`, **una base caída no tumba la API**: ese endpoint responde
503 y los demás siguen funcionando. Esto permite probar la API por tandas,
levantando solo algunas fuentes, y es lo que verifica el endpoint `/salud`.
