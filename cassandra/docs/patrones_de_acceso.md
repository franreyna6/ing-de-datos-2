# Patrones de acceso — Comentarios masivos (Hito 6)

**Grupo N.º 8** · Apache Cassandra · Fixture 2030

Este documento cubre los apartados *Problema de volumen* y *Patrones de acceso* del análisis
(RF3). Se redactó **antes** de fijar las tablas: el modelo de `modelo_tabular.md` sale de estas
preguntas, no de un diagrama de entidades (RNF4).

## 1. Problema de volumen

### 1.1 Qué se necesita

Durante los partidos, miles de personas publican mensajes cortos sobre un partido y otras miles
leen el flujo de mensajes de ese mismo partido. El Hito 1 diagnosticó **Comentarios** como
*mensajes y reacciones en vivo*, con **1 M+ por partido**, **escritura masiva sostenida** y un
**feed en vivo** como consulta típica. El Hito 2 asignó el modelo columnar (Cassandra) y el Hito 3
fijó la postura **AP** (disponibilidad con consistencia eventual) y la partición *por partido +
ventana temporal*.

### 1.2 Supuestos de carga

Los siguientes valores son **supuestos del equipo** para dimensionar el diseño. El de 1 M de
comentarios por partido viene del Hito 1; el resto se deriva de él.

| Supuesto | Valor | Origen |
| :--- | :--- | :--- |
| Comentarios de un partido extremo | 1.000.000 | Hito 1 |
| Duración del flujo de un partido | 140 min (15 de previa + 110 de juego + 15 posteriores) | Supuesto del equipo |
| Escritura promedio del partido extremo | ≈ 119 comentarios/s (1.000.000 / 8.400 s) | Derivado |
| Factor de pico en la ventana más cargada | ≈ 2,6 × el promedio | Medido sobre los datos sintéticos (`distribucion_generada.txt`) |
| Pico estimado de ese partido | ≈ 310 comentarios/s sostenidos durante 5 minutos | Derivado (≈ 93.000 filas en una ventana) |
| Escrituras físicas por comentario | 2 (una por cada tabla de acceso) | Diseño (ver `modelo_tabular.md`) |
| Bytes por fila | ≈ 170 B | **Estimación**, no medición |
| Relación lectura / escritura | Lecturas ≫ escrituras: cada lector actualiza el feed | Enunciado del hito (“alta concurrencia de lectores y escritores”) |

> Estos números sirven para dimensionar el riesgo de hotspot (ver
> `decisiones_de_particionamiento.md`); **no** son una medición del laboratorio. Lo que sí se mide
> en el laboratorio está en `rendimiento.md`.

### 1.3 Por qué una tabla relacional genérica no alcanza

Una tabla `comentarios(id, partido_id, usuario_id, texto, fecha)` con índice por `partido_id`
(el enfoque que el Hito 1 descartó) obliga a mantener índices mientras se escribe a gran ritmo y a
ordenar por fecha en cada lectura. En Cassandra la **forma de lectura** se convierte en la forma
de almacenamiento: las filas se guardan ya agrupadas y ordenadas como se van a leer.

## 2. Patrones de acceso

### 2.1 Lecturas

| ID | Pregunta | Entrada | Orden | Límite | Frecuencia | Estructura | Consulta |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **P1** | ¿Cuáles son los comentarios más recientes de este partido? | `partido_id`, `ventana` actual | Más nuevo primero | 20 | **Muy alta** (cada lector que mira el partido) | `comentarios_por_partido` | `consultas.cql` P1 |
| **P1b** | Seguir el feed hacia atrás cuando la ventana tiene menos de 20 filas | `partido_id`, `ventana` anterior | Más nuevo primero | 20 | Alta | `comentarios_por_partido` | `consultas.cql` P1b |
| **P2** | ¿Qué se escribió en un tramo de tiempo (por ejemplo, tras un gol)? | `partido_id`, `ventana`, rango de `creado_en` | Más nuevo primero | 50 | Media | `comentarios_por_partido` | `consultas.cql` P2 |
| **P3** | ¿Cuál es el historial de comentarios de un usuario? | `usuario_id` (opcional: rango de `creado_en`) | Más nuevo primero | 10 | Media / baja (perfil del usuario) | `comentarios_por_usuario` | `consultas.cql` P3, P3b |
| **P4** | ¿Cuántas filas concentra una ventana? (control de distribución) | `partido_id`, `ventana` | — | — | Operativa, baja | `comentarios_por_partido` | `consultas.cql` P4 |

La **ventana** es el inicio (UTC) del tramo de 5 minutos que contiene al comentario. La aplicación
la calcula a partir de la hora (por ejemplo, 20:23:20 → 20:20:00). Para P1 es la ventana de la
hora actual; para P1b, la inmediatamente anterior, y así hasta completar el límite o llegar al
inicio del partido.

### 2.2 Escrituras

| ID | Operación | Entrada | Tablas que toca | Frecuencia |
| :--- | :--- | :--- | :--- | :--- |
| **W1** | Publicar un comentario | partido, usuario, contenido, instante | Ambas (batch de 2 filas) | **Muy alta**: es el flujo masivo |
| **W2** | Moderar (cambiar `estado`) | clave primaria completa | Ambas (batch de 2 filas) | Baja |
| **W3** | Dar *like* (`likes`) | clave primaria completa | Solo `comentarios_por_partido` | Alta |
| **W4** | Eliminar un comentario puntual | clave primaria completa | Ambas (batch de 2 filas) | Muy baja |

### 2.3 Qué lectura NO se resuelve y por qué

| Necesidad | ¿Por qué no la resuelve el modelo? | Qué correspondería |
| :--- | :--- | :--- |
| Todos los comentarios de un partido sin indicar ventana | La clave de partición `(partido_id, ventana)` queda incompleta; es un reporte, no un feed | Recorrer ventanas desde la aplicación, o una estructura de reporte |
| Cola de moderación (ocultos / pendientes de un partido) | `estado` no integra la clave; exigiría `ALLOW FILTERING` | Tabla propia por estado y partido, con su costo de escritura (no se implementa: queda fuera de las consultas prioritarias) |
| Ranking global de comentarios por *likes* | Agregación global (analítica) | Un motor analítico distinto (ver `decisiones_de_particionamiento.md`, §8) |

El enunciado prohíbe usar `ALLOW FILTERING` como justificación de una consulta frecuente: ninguna
sentencia de `consultas.cql` lo usa.

## 3. Resumen de preguntas → tablas

| Pregunta prioritaria | Tabla | Clave de partición | Clustering |
| :--- | :--- | :--- | :--- |
| P1, P1b, P2, P4 | `comentarios_por_partido` | `(partido_id, ventana)` | `creado_en DESC, comentario_id ASC` |
| P3 | `comentarios_por_usuario` | `usuario_id` | `creado_en DESC, comentario_id ASC` |
