# Modelo tabular — Comentarios masivos (Hito 6)

**Grupo N.º 8** · Apache Cassandra · Fixture 2030

Cubre los apartados *Modelo propuesto* y *Operaciones CQL* del análisis (RF2, RF4, RF5, RF6,
RF10). Los patrones P1–P4 y W1–W4 están definidos en `patrones_de_acceso.md`; el porqué de cada
decisión de partición está en `decisiones_de_particionamiento.md`.

## 1. Keyspace (RF2)

```sql
CREATE KEYSPACE IF NOT EXISTS fixture2030_comentarios
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
```

- **Estrategia:** `SimpleStrategy`. **Factor de replicación:** 1.
- Es una elección **exclusiva del laboratorio de un nodo**. Con una sola copia no hay tolerancia a
  fallas: si el nodo cae, los datos no tienen otra réplica que los sirva. Un despliegue multirregional como el
  del Hito 3 usaría `NetworkTopologyStrategy` con réplicas por datacenter (ver
  `decisiones_de_particionamiento.md`, §6).

## 2. Tablas

### 2.1 `comentarios_por_partido` (tabla principal)

| Columna | Tipo | Rol |
| :--- | :--- | :--- |
| `partido_id` | `text` | **Partición.** Código del partido (`F2030-063`), el mismo del Hito 5 |
| `ventana` | `timestamp` | **Partición.** Inicio (UTC) de la ventana de 5 min que contiene al comentario |
| `creado_en` | `timestamp` | **Clustering.** Instante de creación |
| `comentario_id` | `uuid` | **Clustering.** Identifica el comentario y desempata el mismo instante |
| `usuario_id` | `text` | Autor |
| `contenido` | `text` | Mensaje |
| `estado` | `text` | Moderación: `visible`, `pendiente`, `oculto` (lo valida la aplicación) |
| `likes` | `int` | Métrica de interacción |

```sql
PRIMARY KEY ((partido_id, ventana), creado_en, comentario_id)
WITH CLUSTERING ORDER BY (creado_en DESC, comentario_id ASC)
```

| Elemento | Valor |
| :--- | :--- |
| Clave primaria completa | `((partido_id, ventana), creado_en, comentario_id)` |
| Clave de partición | `(partido_id, ventana)` — compuesta |
| Clustering | `creado_en` (descendente), `comentario_id` (ascendente) |
| Orden de recuperación | Del comentario más nuevo al más viejo dentro de la ventana |
| Atiende | P1, P1b, P2, P4; escrituras W1–W4 |

**Justificación (RF5).** Todas las lecturas del feed parten de un partido y de un tramo de tiempo;
esas dos columnas forman la partición, de modo que cada consulta toca **una sola partición**. El
clustering `creado_en DESC` hace que el “más reciente primero” sea el orden físico: `LIMIT 20` lee
las primeras 20 filas de la partición, sin ordenar. `comentario_id` hace única la fila cuando dos
comentarios comparten el segundo de creación. `partido_id` solo (sin `ventana`) formaría una
partición que crece sin tope; el bucket temporal lo evita (ver §3 de
`decisiones_de_particionamiento.md`).

### 2.2 `comentarios_por_usuario` (estructura de acceso secundaria, RF10)

| Columna | Tipo | Rol |
| :--- | :--- | :--- |
| `usuario_id` | `text` | **Partición** |
| `creado_en` | `timestamp` | **Clustering** |
| `comentario_id` | `uuid` | **Clustering** |
| `partido_id` | `text` | Ubica el comentario en la tabla principal |
| `ventana` | `timestamp` | Ubica el comentario en la tabla principal |
| `contenido` | `text` | Mensaje |
| `estado` | `text` | Moderación (duplicado de la principal) |

```sql
PRIMARY KEY (usuario_id, creado_en, comentario_id)
WITH CLUSTERING ORDER BY (creado_en DESC, comentario_id ASC)
```

**Consulta que la justifica (P3).** “Historial de un usuario”. La tabla principal no la resuelve:
sus comentarios están repartidos en muchas particiones de muchos partidos y no hay forma de
encontrarlos sin recorrerlas todas. Las alternativas eran `ALLOW FILTERING` (descartado por el
enunciado y la Clase 6) o una tabla con otra clave. Se eligió **una tabla adicional**, que es la
técnica que presenta la Clase 6 (“cada consulta de alta frecuencia puede justificar una tabla de
acceso propia”).

**Trade-offs que introduce:**

| Costo | Cómo se controla |
| :--- | :--- |
| Cada comentario se escribe **dos veces** (2× escrituras y 2× almacenamiento) | Es el precio acordado de leer el historial desde una sola partición |
| Las dos copias pueden quedar momentáneamente distintas | Un `BEGIN BATCH` con las dos filas de **un** comentario (atomicidad acotada); la consistencia eventual ya es la postura AP del Hito 3 |
| Sincronizar una métrica que cambia mucho | `likes` **no** se duplica: vive solo en la principal |
| Sincronizar `estado` | Moderar (W2) actualiza las dos tablas en un batch; es infrecuente |
| Partición por usuario sin tope | Los usuarios legítimos escriben pocos comentarios (mediana de 4 y máximo de 2.438 en los datos sintéticos); un usuario automatizado podría crecer sin límite, riesgo asumido y fuera de alcance (control de abuso en la aplicación) |

## 3. Mapa consulta → estructura (RNF4)

| Consulta | Estructura | Sentencia |
| :--- | :--- | :--- |
| P1, P1b — feed | `comentarios_por_partido` | `WHERE partido_id = ? AND ventana = ? LIMIT 20` |
| P2 — tramo de tiempo | `comentarios_por_partido` | `... AND creado_en >= ? AND creado_en < ? LIMIT 50` |
| P3 — historial de usuario | `comentarios_por_usuario` | `WHERE usuario_id = ? LIMIT 10` |
| P4 — tamaño de partición | `comentarios_por_partido` | `SELECT COUNT(*) ... WHERE partido_id = ? AND ventana = ?` |

No existe ninguna tabla sin al menos una consulta que la use.

## 4. Moderación, expiración y borrado

| Criterio | Decisión |
| :--- | :--- |
| Moderación | Por **estado** (`visible` / `pendiente` / `oculto`). Ocultar es un `UPDATE` de `estado`, no un borrado |
| Expiración | **No se usa TTL**: los comentarios del torneo se conservan |
| Borrado | `DELETE` puntual solo para casos excepcionales (W4); nunca masivo |
| Costo aceptado | Cada `DELETE` (y cada fila vencida por TTL) deja un *tombstone* que se procesa al leer y en la compaction. Se evita con el criterio anterior. `crud.cql` (sección E) muestra `USING TTL` solo como demostración de sintaxis |
| Lectura de comentarios moderados | `estado` no integra la clave, por lo que el feed (P1) devuelve también filas `pendiente`/`oculto` y **la aplicación las descarta**. Una página puede traer menos de 20 visibles; es un costo conocido de este diseño |

## 5. Operaciones CQL (propósito de cada archivo)

| Archivo | Sentencias | Propósito |
| :--- | :--- | :--- |
| `scripts/esquema.cql` | `SHOW VERSION`, `CREATE KEYSPACE`, `CREATE TABLE`, `DESCRIBE` | Crear el esquema de forma idempotente (`IF NOT EXISTS`) y dejar constancia de la versión |
| `scripts/carga_muestra.cql` | `BEGIN BATCH … INSERT … APPLY BATCH` | 13 comentarios de muestra para desarrollo; `INSERT` con ids fijos (upsert) |
| `scripts/crud.cql` | `INSERT`, `SELECT`, `UPDATE`, `DELETE`, `USING TTL` | Ciclo completo sobre un comentario de prueba, con clave primaria completa |
| `scripts/consultas.cql` | `SELECT` por partición y rango, `COUNT`, `TRACING` | Consultas P1–P4 y trazado de una lectura |
| `scripts/generar_datos.py` | — | Genera los CSV de la carga masiva (1.100.000) |
| `scripts/carga_o_prueba.*` | `COPY … FROM` | Carga masiva y medición de la tasa de escritura |

Todas las sentencias CQL están comentadas y separadas por tipo de operación (RNF6).

## 6. Sobre el diseño “desde el ER”

El modelo no se derivó de entidades (`Comentario`, `Usuario`, `Partido`) con una clave foránea
entre ellas. Partió de las preguntas P1–P4: de ahí salen dos tablas que **duplican** el comentario
con claves de partición distintas, algo que un modelo relacional normalizado evitaría.
