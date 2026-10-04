# Decisiones de particionamiento — Comentarios masivos (Hito 6)

**Grupo N.º 8** · Apache Cassandra · Fixture 2030

Cubre los apartados *Decisiones de diseño* y *Coherencia con el TPO* del análisis (RF5, RF7,
RNF5). Parte de los supuestos de `patrones_de_acceso.md` §1.2.

## 1. Supuestos de carga que condicionan la partición

| Concepto | Partido extremo (Hito 1) | Partido chico (datos sintéticos) |
| :--- | :--- | :--- |
| Comentarios en el partido | 1.000.000 | 2.401 (el menor del conjunto: `F2030-036`) |
| Duración del flujo | 140 min | 140 min |
| Escritura promedio | ≈ 119 /s | ≈ 0,29 /s |
| Pico de la ventana más cargada | ≈ 2,6 × el promedio | similar proporción |

El diseño debe funcionar en **ambos extremos**: un partido que concentra el tráfico del torneo y
partidos casi vacíos. Una clave que sirva a uno y arruine al otro no es una buena clave.

## 2. Alternativas evaluadas para la clave de partición

### Opción A — `partido_id` solamente (descartada)

Es la clave que muestra el ejemplo de la Clase 6 “para un laboratorio pequeño”. Con el partido
extremo:

- La partición crece a **1.000.000 de filas ≈ 162 MiB** (estimación a ≈ 170 B/fila) y sigue
  creciendo mientras dure el partido.
- **Todas** las escrituras del partido (≈ 119/s en promedio, picos de ≈ 310/s) y todas las
  lecturas del feed caen siempre sobre el mismo conjunto de réplicas: el riesgo de hotspot que
  advierte la Clase 6 (“una partición ilimitada”).
- El partido más popular del torneo es, a la vez, el que más daño recibe.

### Opción B — `(partido_id, ventana)` con ventanas de 5 minutos (elegida)

El *bucket* temporal convierte una partición ilimitada en una **secuencia de particiones
acotadas**: cada 5 minutos el partido pasa a escribir en otra partición (y, potencialmente, en
otro conjunto de réplicas). Es la estrategia de *sub-partición por ventana temporal* que el Hito 3
dejó planteada de forma conceptual y que este hito implementa.

### Opción C — agregar un `shard` a la partición (no implementada; criterio de escalamiento)

Añadir un número `shard` (0 … N−1, por ejemplo `hash(usuario_id) % N`) a la clave de partición
repartiría la escritura de **una misma ventana** entre N particiones. Costo: cada lectura del feed
debe consultar N particiones y combinar los resultados en la aplicación. **No se implementa
porque con la ventana de 5 minutos el pico estimado queda por debajo del umbral de revisión
(§4)**, pero queda declarada como siguiente paso si la carga real lo supera.

## 3. Elección del tamaño de ventana

Cálculo para el partido extremo (1.000.000 de comentarios en 140 min, pico ×2,6, ≈ 170 B/fila):

| Ventana | Filas promedio por partición | Filas en el pico | Tamaño estimado en el pico | Filas promedio, partido chico |
| :--- | :--- | :--- | :--- | :--- |
| Sin bucket (Opción A) | 1.000.000 | 1.000.000 | ≈ 162 MiB | 2.401 |
| 15 min | ≈ 107.000 | ≈ 279.000 | ≈ 45 MiB | ≈ 257 |
| **5 min (elegida)** | **≈ 35.700** | **≈ 93.000** | **≈ 15 MiB** | **≈ 86** |
| 1 min | ≈ 7.100 | ≈ 18.600 | ≈ 3 MiB | ≈ 17 |

- Con **1 minuto** las particiones son más pequeñas, pero en un partido poco concurrido una
  ventana tiene unas 17 filas: un feed de 20 comentarios necesitaría **dos o más particiones**
  casi siempre (y más en la previa y el cierre), con lo que se pierde la ventaja “una consulta,
  una partición”.
- Con **15 minutos** el pico de un partido extremo supera las 270.000 filas por partición.
- **5 minutos** mantiene el partido extremo en decenas de miles de filas por partición y deja a un
  partido chico con ≈ 86 filas por ventana, suficientes para llenar un feed de 20 sin cruzar
  particiones.

El tamaño de ventana es una constante de la aplicación (`VENTANA_MIN` en `generar_datos.py`, y el
cálculo de `ventana` en los clientes). Cambiarla afecta solo a los comentarios nuevos.

**Verificación sobre los datos generados** (`evidencia/distribucion_generada.txt`, 1.100.000 de
filas en 96 partidos): 2.688 particiones; filas por partición con mediana 215, p99 3.250 y
**máximo 12.087** (≈ 2,0 MiB estimados) en la ventana de las 20:45 de `F2030-063` (goles de los minutos 46 y 49), el
partido de mayor popularidad. Los números reales del nodo se miden en `rendimiento.md`.

## 4. Umbral de revisión (criterio propio del equipo)

Se define como **umbral de revisión** que, si la carga estimada de una ventana supera
**≈ 100.000 filas** (≈ 16 MiB) o **≈ 500 escrituras/s sobre una misma partición**, se debe
reducir la ventana (a 1 minuto) o aplicar la Opción C. Es una cota de trabajo elegida por el
equipo para el laboratorio, **no un límite de Cassandra**. Con los supuestos de §1 el pico del
partido extremo (≈ 93.000 filas, ≈ 310 escrituras/s) queda **cerca pero por debajo** del
umbral: es un margen estrecho y por eso queda registrado como riesgo.
Esto responde la decisión pendiente del Hito 3 (“umbral de sub-partición”) para Comentarios.

**Hotspot residual:** dentro de una misma ventana, todas las escrituras de un partido van a una
sola partición. La ventana reparte la carga **a lo largo del tiempo**, no **dentro** de un
mismo instante.

## 5. Clustering, duplicación y tombstones

- **Clustering `creado_en DESC, comentario_id ASC`.** El orden físico coincide con el orden de
  lectura del feed; `comentario_id` desempata sin necesidad de `ALLOW FILTERING`.
- **Duplicación controlada (`comentarios_por_usuario`).** Es una decisión deliberada: se paga el
  doble de escritura y almacenamiento a cambio de resolver P3 en una partición. Qué se duplica
  y por qué `likes` no, está en `modelo_tabular.md` §2.2.
- **TTL y DELETE.** No se usa TTL y el borrado físico es puntual; la moderación se hace por
  `estado`. Motivo: ambos producen tombstones que se procesan en lecturas y compaction.

## 6. Replicación y consistencia: laboratorio vs. producción

| Aspecto | Laboratorio (este hito) | Producción (Hito 3) |
| :--- | :--- | :--- |
| Nodos | 1 | Varios, en 6 regiones |
| Estrategia del keyspace | `SimpleStrategy` | `NetworkTopologyStrategy`, réplicas por datacenter |
| Factor de replicación | 1 (una sola copia) | Mayor que 1 por datacenter |
| Tolerancia a fallas | Ninguna | Otras réplicas siguen sirviendo si cae un nodo |
| `CONSISTENCY ONE` / `QUORUM` / `ALL` | Equivalentes: hay una sola réplica | Cada nivel exige un número distinto de réplicas |

El nodo único **no demuestra** disponibilidad ni tolerancia a fallas; solo permite aprender CQL y
validar el modelo.

**Postura para Comentarios (Hito 3): AP.** Se prioriza aceptar la escritura sin esperar a todas las
réplicas: **W bajo** (`ONE`) y lectura tolerante, de modo que **R + W ≤ N** y no hay garantía de
leer lo último escrito. El costo se acepta de forma explícita:

- un comentario puede tardar fracciones de segundo en verse en todas las regiones;
- el orden de aparición puede no ser idéntico entre regiones;
- un comentario confirmado por una sola réplica **podría perderse** si esa réplica falla antes de
  copiarse a las demás. Para mensajes de un feed en vivo se considera tolerable; no sería
  aceptable para un dato que exija no perder ningún registro, y esos datos están **fuera del
  alcance** de este hito.

Los scripts usan `CONSISTENCY ONE`, coherente con esta postura.

## 7. Coherencia con los hitos anteriores

| Hito | Qué se tomó | Cómo se refleja aquí |
| :--- | :--- | :--- |
| 1 — Análisis | Comentarios: 1 M+ por partido, escritura masiva sostenida, feed en vivo | Supuestos de carga (§1) y patrón P1 |
| 2 — Matriz | Modelo columnar (Cassandra) para Comentarios | Tecnología de este hito |
| 3 — Arquitectura | AP, sin nodo maestro, partición por partido + ventana, W bajo, “umbral de sub-partición” pendiente | §2 (Opción B), §4 y §6 |
| 5 — Grafos | Códigos de partido `F2030-xxx`, fechas, goles y tarjetas de los 96 partidos | Los CSV de `data/origen/` son los de `import/` del Hito 5; los picos de actividad del generador siguen los minutos de goles y tarjetas |

Este hito **no** reutiliza datos del Hito 4 (equipos y jugadores en MongoDB) ni agrega
funcionalidad fuera de comentarios: no hay API, caché, series temporales ni monitoreo.

## 8. Respuestas a las preguntas guía

| # | Pregunta | Respuesta breve |
| :--- | :--- | :--- |
| 1 | Consultas durante un partido con el menor número de particiones | P1 y P2 tocan **una** partición; P1b, una por ventana adicional |
| 2 | Clave de partición y riesgo | `(partido_id, ventana)`; riesgo: hotspot residual dentro de una ventana (§4) |
| 3 | Clustering y orden | `creado_en DESC, comentario_id ASC`: del más nuevo al más viejo |
| 4 | ¿Por qué el historial por usuario requiere otra estructura? | Los comentarios del usuario están repartidos entre muchas particiones; ver `modelo_tabular.md` §2.2 |
| 5 | Límite esperado por partición | ≈ 93.000 filas ≈ 15 MiB y ≈ 310 escrituras/s en el pico del partido extremo (estimaciones) |
| 6 | Evitar que un partido popular concentre la carga | Bucket de 5 minutos; escalamiento por ventana más corta o `shard` (§2, §4) |
| 7 | Qué expira y costo de tombstones | Nada expira; borrado puntual; la moderación usa `estado` (§5) |
| 8 | Qué consulta justifica la tabla adicional | P3, historial por usuario |
| 9 | Replicación de laboratorio vs. multirregional | §6 |
| 10 | Qué medición sostiene el comportamiento bajo carga | Tasa de `COPY`, conteo de filas por partición y verificación esperado/observado (`rendimiento.md`) |
| 11 | Supuestos de la prueba a registrar | Ambiente, recursos, versión, parámetros de `COPY` y estado inicial de las tablas (`rendimiento.md`) |
| 12 | Cambios si el módulo debe servir reportes analíticos históricos | Ver abajo |

**Pregunta 12.** Un reporte histórico (por ejemplo, comentarios por partido y por hora, o los
más votados del torneo) necesita recorrer muchas particiones: es el patrón que la Clase 6 asigna
a un **motor analítico**, no a una tabla de Cassandra orientada por consulta. Se debería mantener
el módulo transaccional tal como está y exportar los datos a un almacén analítico, o escribir
una tabla adicional de resumen en el momento de cada publicación (con el costo de escritura
correspondiente). Ninguna de las dos opciones se implementa en este hito.
