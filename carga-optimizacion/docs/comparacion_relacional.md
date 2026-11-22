# Comparación con una alternativa relacional (RF14)

> **Análisis conceptual, no experimental.** No se implementó ni se midió una base relacional. Ninguna afirmación de esta sección es un resultado medido; los resultados medidos están solo en `docs/evidencia/`.

La comparación se hace sobre **el mismo flujo**: publicar y leer los comentarios recientes de un partido durante el pico posterior a un gol.

## 1. Modelo relacional equivalente

**Unidad de información**: un comentario, una fila.

```text
PARTIDO(partido_id PK, fecha, fase, ...)
COMENTARIO(
  comentario_id  PK,                   -- identificador generado por el cliente
  partido_id     FK -> PARTIDO,
  creado_en      timestamp NOT NULL,
  usuario_id     NOT NULL,
  contenido      NOT NULL,
  estado, likes
)
INDICE (partido_id, creado_en DESC)    -- sirve la lectura "ultimos N del partido"
```

| Operación del flujo | Relacional | Cassandra (actual) |
| :--- | :--- | :--- |
| Publicar | `INSERT INTO COMENTARIO ...`, una transacción. Actualiza la tabla y el índice, y verifica la FK del partido. | `INSERT` en la partición (`partido`, `ventana`). No verifica que el partido exista. |
| Leer los recientes | `SELECT ... WHERE partido_id = ? ORDER BY creado_en DESC LIMIT 20`, por el índice. Sirve sin importar la ventana de 5 minutos. | `SELECT ... WHERE partido_id = ? AND ventana = ? LIMIT 20`: solo la ventana actual. Al empezar una ventana nueva, la lista arranca vacía. |
| Reintento con el mismo `comentario_id` | El segundo `INSERT` viola la PK y se rechaza. La **idempotencia sale del modelo**. | Crea otra fila, porque `creado_en` forma parte de la clave. Ver el hallazgo en `integridad_y_limitaciones.md`. |
| Joins | Directos: comentario, partido y equipo en una sola consulta. | No existen. Se resuelven en la aplicación o en el Data Mart. |

## 2. Garantías esperadas

- **Relacional**: ACID en un solo motor. Al confirmar el `201`, el comentario es visible para la siguiente lectura (consistencia inmediata), la FK impide comentarios de partidos inexistentes y la PK impide duplicados.
- **Cassandra (un nodo en el laboratorio)**: cada escritura es atómica dentro de su partición. Con réplicas, la consistencia depende del nivel elegido; según la corrección del Hito 3, si no se alcanza el quórum se acepta indisponibilidad de escritura. No hay integridad referencial ni unicidad de `comentario_id` fuera de la clave.
- **Con la caché del Hito 12**, ninguna de las dos alternativas da lectura inmediata: el lector puede ver hasta 2 s de atraso. La caché cambia la garantía de lectura en las dos.

## 3. Cómo crecería con volumen y concurrencia

| Aspecto | Relacional | Cassandra |
| :--- | :--- | :--- |
| Escrituras concentradas en un partido | Todas van a la misma tabla y al mismo extremo del índice ordenado por tiempo. Con mucha concurrencia, aparece contención sobre esa zona del índice y sobre el registro de transacciones. Escalar escrituras suele ser vertical, con una máquina más grande; existen estrategias horizontales, pero agregan complejidad. | La partición caliente cae en las réplicas que le corresponden. Distribuir otros partidos es natural (partición por `partido` y `ventana`), pero **la partición caliente no se reparte**: el partido del gol sigue cayendo en los mismos nodos. La `ventana` de 5 minutos acota el tamaño de la partición. |
| Lecturas repetidas | Se pueden repartir en réplicas de lectura, con retraso de replicación, o se puede usar la misma caché. | Se pueden repartir entre réplicas según la consistencia elegida, o se puede usar la misma caché. |
| Histórico (más de 1.000.000 de comentarios) | La tabla y el índice crecen. La consulta por índice sigue acotada, pero el mantenimiento del índice y el espacio aumentan. | Cada partición queda acotada por la ventana. El volumen total se reparte entre nodos. |

**El cuello de botella observado en este hito, las lecturas repetidas de la misma página, es igual en las dos alternativas.** La caché lo ataca antes de llegar a la base, sea cual sea el motor.

## 4. Qué parte del flujo es más simple o más compleja

- **Más simple en relacional**: la idempotencia de los reintentos, la verificación de que el partido existe, leer "los últimos N" sin el corte de la ventana, y los reportes con joins (el Data Mart entra naturalmente en un esquema dimensional relacional).
- **Más simple en Cassandra**: absorber muchas escrituras repartidas entre partidos y nodos sin coordinar transacciones, y acotar cada lectura a una sola partición conocida.

## 5. En qué condiciones conviene cada alternativa

**Relacional**, cuando:

- el volumen de escritura entra en un solo servidor;
- importa que no haya duplicados ni comentarios huérfanos;
- se necesita consistencia inmediata, por ejemplo moderación o un comentario que tiene que verse apenas se publica;
- el mismo dato alimenta reportes con joins.

Es la opción natural para el **Data Mart** de este hito.

**Cassandra**, cuando:

- las escrituras de todo el torneo superan lo que absorbe un servidor;
- se necesita disponibilidad con varios nodos;
- el acceso es siempre por una clave conocida (`partido`, `ventana`);
- se acepta resolver la idempotencia y las referencias en la aplicación o en el modelo de clave.

**Combinación**: Cassandra en el camino operacional del feed y una estructura relacional o dimensional en el camino analítico, alimentada por el ETL de `integracion_data_mart.md`.

## 6. Qué no se pudo medir

- La latencia y el throughput de una base relacional bajo el mismo escenario: no se implementó.
- El comportamiento con réplicas y varios nodos, tanto en Cassandra como en relacional: el laboratorio usa un solo nodo.
- La contención del índice relacional con el patrón de escritura concentrada.
- La latencia de red entre regiones.

Por lo tanto, **no se afirma que una alternativa sea superior en términos absolutos**. La elección depende del volumen de escritura, de la garantía de consistencia requerida y del patrón de acceso (Clase 13).
