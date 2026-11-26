# Hito 4 — Decisiones Documentales del Módulo de Equipos y Jugadores

**Grupo N.º 8** · Clase 4 · Fixture 2030

---

## Sección 1 — Punto de partida y trazabilidad con hitos previos

Este módulo aterriza tres decisiones ya tomadas y que **no se revisan** en este hito:

- **Hito 1** identificó que Equipos y Jugadores son datos de volumen fijo y chico (64 y ~1.500), alta lectura y baja frecuencia de escritura, con relaciones simples entre sí. En la matriz de trade-offs se aceptó BASE por sobre ACID estricto en el conjunto de la arquitectura, aunque estos datos específicos toleran menos desactualización que otros (resultados oficiales, ranking).
- **Hito 2** eligió **MongoDB** (Documental) sobre ese conjunto de datos por su ajuste al patrón "documento autocontenido con estructura anidada, sin JOINs, esquema flexible" (resultado ponderado 4,10 en la matriz de decisión).
- **Hito 3** posicionó a Información deportiva como el **único subsistema CP** de la arquitectura, con **réplica completa por región** (sin particionar, por bajo volumen) y confirmación de escrituras por mayoría de réplicas. Además dejó **pendiente** desde el Hito 2 la definición de una **convención de identificadores reutilizable por Neo4j** (Hito 5) e IRIS.

Sobre esa base, este hito toma cinco decisiones de implementación, cada una respondiendo a un requisito funcional y con impacto medible.

---

## Sección 2 — Tabla de decisiones (plantilla del enunciado)

| Decisión | Alternativas consideradas | Elección | Justificación | Impacto esperado |
| --- | --- | --- | --- | --- |
| **1. Relación equipo ↔ jugador** | (a) Embedding: array de jugadores dentro del documento del equipo. (b) Referencing puro: colecciones separadas, `jugadores.equipoCodigo` apunta a `equipos.codigo`. (c) Híbrido: referencing + resumen embebido. | **(b) Referencing puro** con dos colecciones separadas. | Los jugadores se consultan individualmente (ficha en vivo, ranking global de valor de mercado, filtrado por posición cross-equipo). Con embedding, actualizar UN jugador implica reescribir el documento del equipo entero (16-30 KB) para tocar un campo de 20 bytes. Además, el Hito 3 exige que Neo4j (Hito 5) modele jugador y equipo como nodos separados con relaciones explícitas: mantener colecciones separadas en MongoDB facilita esa proyección hacia el grafo. La contra clásica de referencing —"múltiples consultas"— se mitiga con `$lookup` para las pocas vistas que necesitan un plantel completo, y no aplica cuando la consulta es sobre un solo jugador o un ranking cross-equipo. | Lectura de un jugador individual sin traer nada del equipo → payload menor y `explain` de tipo `IXSCAN` sobre `codigo` (unique). Lectura de plantel completo requiere una segunda consulta / `$lookup`, aceptable porque en Hito 3 los partidos operativos vivirán en Neo4j, no acá. |
| **2. Validación documental** | (a) Sin validación (esquema flexible puro). (b) Validación en la app antes de escribir. (c) **JSON Schema en la colección** (`validator` + `validationAction: "error"`). | **(c) JSON Schema con `validationAction: "error"`.** | Es la única opción que garantiza integridad **aunque la app tenga bugs, aunque alguien escriba directamente con `mongosh`, y aunque haya carga desde un script terceros**. La flexibilidad de MongoDB es una virtud, pero el enunciado exige "reglas de validación para los atributos críticos" (RF7) y "integridad documental" (RNF3). El schema fuerza tipos, enums (confederación, posición, pie hábil), patrones (código FIFA `^[A-Z]{3}$`, dorsal en 1..99), rangos (altura, peso, ranking) y campos requeridos. Se elige `strict + error` (no `warn`) porque en producción es preferible fallar rápido a acumular datos corruptos silenciosos. | Cualquier intento de insertar un documento inválido produce excepción documentada; en `scripts/03-operaciones-crud.js` se demuestra explícitamente rechazando `confederacion:"SUDAMERICANA"`. Costo: cada `insertOne` paga una validación (µs), despreciable frente al beneficio. |
| **3. Estrategia de identificadores** | (a) Solo `_id` autogenerado (ObjectId). (b) Sobrescribir `_id` con un string propio. (c) Mantener `_id` = ObjectId **y** un `codigo` de negocio con índice único. | **(c) `_id` ObjectId + `codigo` unique de negocio.** Para equipos: `codigo` = código FIFA de 3 letras (ARG, BRA, ESP…). Para jugadores: `codigo` = `[EQUIPO]-[dorsal]-[slug6]`, p. ej. `ARG-10-emtxem`. | Un `_id` ObjectId sigue siendo útil para operaciones internas y `$lookup` y no impone conocimiento externo; un `codigo` humano-legible y estable es lo que la app, la URL y el resto de los motores (Neo4j en Hito 5) van a citar. El código FIFA es universal, público y raramente cambia; ancla la coherencia entre motores sin acoplarlos. El sufijo `slug6` en jugadores previene colisiones cuando un jugador cambia de dorsal (el dorsal no puede ser identidad; el slug sí). Además, dos índices únicos cierran huecos: `codigo` (identidad de negocio) y `(equipoCodigo, dorsal)` (no puede haber dos dorsales 10 en Argentina). | Resuelve el **pendiente del Hito 2** sobre convención de identificadores reutilizable. En el Hito 5, Neo4j creará nodos `Equipo{codigo:"ARG"}` y `Jugador{codigo:"ARG-10-emtxem"}` referenciando exactamente los mismos strings. Cero migraciones, cero mapeos. |
| **4. Índices principales** | (a) Solo `_id` (default). (b) Un índice por atributo consultable. (c) **Set mínimo dirigido por consultas reales.** | **(c) Siete índices**, cada uno atado a una consulta concreta (ver §3). | Un índice por atributo penaliza la escritura y ocupa memoria sin beneficio si nadie consulta por ese campo. El set mínimo cubre las consultas frecuentes (`codigo`, `equipoCodigo`, `equipoCodigo+dorsal`, `equipoCodigo+posicion`), las de negocio (ranking por confederación, top valor de mercado, anfitriones), y agrega dos índices únicos que además hacen de guardián de integridad. El orden de las claves de los índices compuestos respeta la regla **ESR** (Equality, Sort, Range) de MongoDB. | La consulta más frecuente ("plantel completo de un equipo, ordenado por posición") pasa de COLLSCAN sobre 1.024 documentos a IXSCAN sobre 16 → ~64× menos documentos examinados y sin `SORT` en memoria. Ver `scripts/06-analisis-rendimiento.js`. |
| **5. Carga y actualización** | (a) `insertMany` a una colección vacía. (b) `mongoimport --drop`. (c) **`bulkWrite` con `updateOne` + `upsert:true` matcheando por `codigo`.** | **(c) `bulkWrite` upsert idempotente.** | (a) explota si la carga se corre dos veces (`E11000 duplicate key`). (b) borra la colección entera, incompatible con RF8 ("no debe generar duplicados ni inconsistencias" **al re-ejecutar**, no "empezar de cero"). La opción (c) es la única que soporta re-ejecución segura: si el `codigo` ya existe, actualiza; si no, inserta. Los datos se generan con semilla fija (`random.seed(2030)`) en `data/generar_datos.py`, así que dos regeneraciones producen JSON idénticos. El `bulkWrite` con `ordered:false` permite continuar aunque un documento particular falle validación, y devuelve el detalle. | Cumple RF8 y RNF1: un integrante externo clona, ejecuta `./run-all.sh`, y obtiene exactamente el mismo estado, ejecute una o cinco veces. Al final de la carga se verifican explícitamente: total de documentos, huérfanos, duplicados de `codigo`, y colisiones `(equipoCodigo, dorsal)`. |

---

## Sección 3 — Detalle de los siete índices

Cada índice está en `scripts/02-crear-indices.js` con comentario individual.

| # | Colección | Definición | Consulta que sostiene | Tipo |
| --- | --- | --- | --- | --- |
| 1 | `equipos` | `{ codigo: 1 }` UNIQUE | `findOne({codigo:"ARG"})`, upsert por `codigo`, `$lookup` desde `jugadores` | Simple + unique |
| 2 | `equipos` | `{ confederacion: 1, rankingFIFA: 1 }` | "top N equipos de UEFA/CONMEBOL/…" (filtro + sort) | Compuesto (ESR) |
| 3 | `equipos` | `{ anfitrion: 1 }` con `partialFilterExpression: { anfitrion: true }` | Listar las 6 sedes anfitrionas | **Parcial** |
| 4 | `jugadores` | `{ codigo: 1 }` UNIQUE | `findOne({codigo:"ARG-10-…"})`, upsert por `codigo` | Simple + unique |
| 5 | `jugadores` | `{ equipoCodigo: 1, posicion: 1 }` | "plantel de un equipo" (opcional filtro por posición) | Compuesto (ESR) |
| 6 | `jugadores` | `{ equipoCodigo: 1, dorsal: 1 }` UNIQUE | `findOne({equipoCodigo:"ARG", dorsal:10})` **y** guardián de integridad | Compuesto unique |
| 7 | `jugadores` | `{ valorMercado_millonesEUR: -1 }` | Ranking global de valor de mercado, con paginación | Simple |

**Por qué no más**: el enunciado ("un índice no es una mejora automática") advierte sobre el costo de índices sin uso. Se descartaron índices sobre `nombre` (no hay búsqueda por texto en este hito), `nacionalidad DT`, `colores`, `edad`, `peso_kg`, `altura_cm` — no hay consulta que los use como predicado principal.

**Nota sobre paginación profunda**: la ordenación por `valorMercado_millonesEUR` con `skip+limit` es óptima para paginas 1–20; para paginación profunda (miles de páginas) convendría **keyset pagination** usando el último valor como cursor. No se implementa acá porque el módulo tiene 1.024 jugadores y la profundidad real no llega a exigirlo.

---

## Sección 4 — Trade-offs aceptados

- **Integridad referencial no automática**: MongoDB no impone que `jugadores.equipoCodigo` exista en `equipos.codigo`. Se compensa: (i) validando en el schema el **formato** del código (regex `^[A-Z]{3}$`); (ii) verificando explícitamente al final de la carga que no queden huérfanos; (iii) usando `codigo` FIFA que es un espacio fijo y humano-legible. En producción, la app haría la validación cruzada antes de insertar.
- **Consistencia eventual entre réplicas** (Hito 3): en un despliegue multi-región un `find` de un equipo podría devolver una versión ligeramente anterior a la escritura confirmada por mayoría. Se acepta por el bajo ratio de escritura de estos datos (un cambio de DT o de ranking no ocurre a cada segundo).
- **Duplicación mínima**: `equipoCodigo` se repite ~16 veces por equipo dentro de `jugadores` (~16 KB extra en total). Aceptable: el ahorro operativo del referencing y la simplicidad para el `$lookup` compensa varios órdenes de magnitud.
- **`_id` ObjectId "invisible"**: la app trabaja con `codigo` y podría notarse que hay dos identificadores. Se prefiere pagar esa mínima incomodidad a acoplar el `_id` interno de MongoDB al código de negocio (que si algún día cambiara —por ejemplo, migración de FIFA a otra taxonomía— rompería referencias externas).

---

## Sección 5 — Cómo se cumplen los criterios de evaluación de la Clase 4

| Criterio | Peso | Cómo se cubre |
| --- | --- | --- |
| Diseño documental | 25% | Este documento (5 decisiones + índices + trade-offs); JSON Schema estricto en `init-scripts/01-init-database.js` |
| Funcionalidad | 35% | 64 equipos + 1024 jugadores + operaciones CRUD + validación demostrada; verificación post-carga automática; `run-all.sh` end-to-end |
| Rendimiento | 25% | 7 índices con justificación 1-a-1; `06-analisis-rendimiento.js` con `explain("executionStats")` antes/después; agregaciones que aprovechan índices existentes |
| Documentación | 15% | Este documento + README con instrucciones paso a paso + evidencia capturada en `evidencia/` |

---

## Sección 6 — Vínculo explícito con los hitos previos (RNF5)

| Hito previo | Elemento retomado | Cómo se manifiesta en este módulo |
| --- | --- | --- |
| Hito 1 (Análisis) | "Equipos y Jugadores: 64 y 1500+ registros, nulo crecimiento, lectura alta" | Volumen exacto en la carga; índices priorizando lectura sobre escritura |
| Hito 1 (Análisis) | "Ficha en vivo del jugador" como patrón de consulta | Índice único sobre `codigo` de jugador + índice compuesto `(equipoCodigo, dorsal)` |
| Hito 2 (Matriz) | Elección de MongoDB con puntaje 4,10 por C3 y C4 | Este módulo entero materializa esa decisión con documentos anidados (subdocumento `directorTecnico`, arrays `colores`) que un modelo relacional no expresa de forma natural |
| Hito 2 (Pendiente) | "Convención de identificadores reutilizable por Neo4j e IRIS" | Resuelto en la Decisión #3 |
| Hito 3 (CAP) | Información deportiva es CP; escritura confirmada por mayoría de réplicas | Este hito trabaja monoinstancia (RF1), pero el schema y los identificadores están preparados para un replica set (todos los índices compuestos se comportan igual, `_id` sigue siendo global) |
| Hito 3 (Sin particionar) | Volumen fijo y chico → réplica completa por región, no sharding | Se refleja en que **ningún índice se diseñó como shard key**, y todas las consultas asumen la colección completa localmente |
| Hito 3 (Sincronización de IDs) | Riesgo de desalinear equipos entre MongoDB y Neo4j si cambia un plantel | El campo `codigo` FIFA de tres letras funciona como identificador cross-motor; Neo4j (Hito 5) usará exactamente el mismo string como propiedad de nodo |

---

## Sección 7 — Limitaciones y qué queda para hitos futuros

- **Datos sintéticos**: los nombres de jugadores no son reales; los datos deportivos deportivos (código FIFA, confederación, ranking) sí. En un despliegue real, la carga inicial vendría de una fuente autoritativa (API FIFA o alimentación manual).
- **Sin transacciones multi-documento**: no se necesitaron en este módulo (una entidad = un documento). Cuando el Hito 5 traiga Neo4j al escenario, la actualización de plantel deberá ser atómica **entre motores** — es el pendiente que arrastra este hito.
- **Sin shard key**: definir shard key sería prematuro con 64 + 1.024 documentos. Si a futuro se sumaran datos históricos por jugador (ficha histórica de varios torneos), la shard key natural sería `equipoCodigo` (o directamente moverlo a Cassandra, como planteó el Hito 2 para auditoría/históricos).
- **Sin replica set operativo**: `docker-compose.yml` levanta un `mongod` standalone. Simular un replica set multi-nodo excede el tiempo de clase (RNF8: 90 minutos) y no cambia el modelo documental. Está previsto para el hito de despliegue distribuido.
- **Sin cifrado en reposo ni TLS**: fuera del alcance académico del hito, siempre presente en la lista de "mejoras para producción" del propio material de clase.
