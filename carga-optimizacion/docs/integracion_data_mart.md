# Integración analítica: Data Mart de actividad alrededor de los goles (RF12, RF13, RNF12)

> Esta sección es una **propuesta de diseño**: no se construyó ni se midió. Lo que sigue es análisis conceptual, separado de los resultados de la prueba de carga.

## 1. Pregunta analítica

> **¿Cuánto aumenta la actividad de comentarios en los 5 minutos posteriores a cada gol, respecto de los 5 minutos previos, por partido, por fase y por equipo que convirtió?**

La pregunta sale directamente del flujo probado. Sirve al equipo de producto para dimensionar los picos, porque indica cuánto hay que multiplicar la capacidad de lectura y escritura después de un gol, y para comparar partidos y fases.

## 2. Por qué no se responde consultando las fuentes operacionales

Para responderla en tiempo de consulta, la API tendría que:

- leer en Cassandra **todas** las particiones de 5 minutos de cada partido del torneo (unas 25 por partido, unas 2 horas con el entretiempo) y contar las filas;
- recorrer en Neo4j los eventos de tipo gol de cada partido hasta el jugador y su equipo;
- buscar en MongoDB los atributos del equipo;
- cruzar los tiempos en la aplicación.

Cada reporte repetiría miles de lecturas sobre la misma tabla que atiende el feed en vivo. Es el antipatrón de la *consulta universal* de la Clase 13: competiría con el camino operacional que esta prueba de carga busca proteger.

Con una proyección analítica, el conteo se calcula **una vez** por ventana cerrada y el reporte lee una tabla chica, ya agregada.

## 3. Fuentes y procedencia

| Dato | Fuente operacional | Estructura de origen | Cómo se extrae |
| :--- | :--- | :--- | :--- |
| Comentarios (`comentario_id`, `creado_en`, `usuario_id`, `estado`) | **Cassandra** (Hito 6) | `comentarios_por_partido`, partición (`partido_id`, `ventana`) | Por partición conocida: para cada partido activo y cada ventana **cerrada** desde la última marca de agua. Nunca con `ALLOW FILTERING`. |
| Partido (código, fecha, fase, grupo, sede) | **Neo4j** (Hito 5) | Nodo `Partido` | `MATCH (p:Partido {codigo: $codigo})` |
| Goles (minuto, jugador, equipo) | **Neo4j** (Hito 5) | `(Evento {tipo:'Gol'})-[:OCURRE_EN]->(Partido)`, `(Evento)-[:PROTAGONIZADO_POR]->(Jugador)-[:PERTENECE_A]->(Equipo)` | Una consulta por partido con eventos nuevos. |
| Atributos de equipo (nombre, confederación) | **MongoDB** (Hito 4) | Colección `equipos` | Lectura completa: son 64 documentos y cambian muy poco. |
| Instante de inicio real del partido | **Dato faltante** | Hoy ninguna fuente lo guarda: `Partido` tiene solo la fecha. | Se agrega como tabla de referencia cargada desde el calendario oficial del torneo, con su propio lote y su fecha de carga. |

**Qué no se integra.** Ni las sesiones ni la caché de Redis. Son estado efímero con TTL: no permiten reconstruir un histórico, y la pregunta no las necesita (Clase 13: *no todo debe copiarse*). Tampoco las estadísticas de InfluxDB ni las entidades de IRIS, porque la pregunta no las requiere.

## 4. Modelo dimensional

**Dimensiones**

- `DIM_PARTIDO`: `partido_id` (código del fixture, por ejemplo `F2030-001`), `fecha`, `fase`, `grupo`, `sede`, `inicio_utc` (referencia), `equipo_local_id`, `equipo_visitante_id`, `fuente`, `lote_carga`.
- `DIM_EQUIPO`: `equipo_id` (código FIFA, por ejemplo `ARG`), `nombre`, `confederacion`, `fuente`, `lote_carga`.

**Hechos**

- `FACT_COMENTARIOS_MINUTO`. **Grano: una fila por partido y por minuto de reloj UTC.** Columnas: `partido_id`, `minuto_utc`, `minuto_de_partido` (derivado), `n_comentarios`, `n_usuarios_distintos`, `fuente='cassandra'`, `lote_carga`, `fecha_extraccion`.
- `FACT_GOL`. **Grano: una fila por gol.** Columnas: `evento_id`, `partido_id`, `equipo_id`, `jugador_id`, `minuto`, `fuente='neo4j'`, `lote_carga`.

**Vista de respuesta**

- `VISTA_ACTIVIDAD_POST_GOL`. **Grano: una fila por gol.** Columnas: `evento_id`, `partido_id`, `fase`, `equipo_id`, `minuto`, `comentarios_5min_antes`, `comentarios_5min_despues`, `variacion_relativa`.
- Se calcula sumando `FACT_COMENTARIOS_MINUTO` en `[minuto−5, minuto)` y `[minuto, minuto+5)` del mismo partido.

Las medidas son **sumables** dentro de un partido, porque cada comentario se cuenta en exactamente un minuto. `n_usuarios_distintos` **no es sumable** entre minutos: se recalcula, no se suma.

## 5. Transformaciones

1. **Filtrar** partidos de laboratorio: se descartan los `partido_id` que no existen en `DIM_PARTIDO`, por ejemplo los `H12-*` de esta prueba. Se cuentan en el registro del lote como *referencia inválida*.
2. **Filtrar estado**: solo comentarios con `estado = 'visible'`.
3. **Deduplicar** por `comentario_id`, conservando el `creado_en` más antiguo. Esto corrige los duplicados por reintento detectados en `integridad_y_limitaciones.md`.
4. **Normalizar el tiempo**: todos los instantes en UTC. Se calcula `minuto_utc = truncar(creado_en, minuto)`.
5. **Derivar el minuto de partido**: `minuto_de_partido = (minuto_utc − inicio_utc)` en minutos. *Limitación*: no descuenta el entretiempo ni el tiempo agregado, porque las fuentes no los registran. Se documenta como aproximación y, para el segundo tiempo, se corrige con el entretiempo reglamentario de 15 minutos.
6. **Agregar** por (`partido_id`, `minuto_utc`): `n_comentarios` y `n_usuarios_distintos`.
7. **Unir** con las dimensiones por clave de correspondencia:
   - `partido_id` de Cassandra = `Partido.codigo` de Neo4j (el mismo formato `F2030-NNN`);
   - `Equipo.codigo` de Neo4j = `codigo` de MongoDB (código FIFA).

## 6. Flujo de actualización (ETL incremental)

```text
cada 5 minutos durante los partidos (y un lote final por partido):
  marca = leer_checkpoint("comentarios")              # ultima ventana cerrada procesada
  ventanas = ventanas cerradas desde marca - 2 ventanas (gracia para datos tardios)
  para cada partido activo y cada ventana:
      filas = Cassandra: SELECT ... WHERE partido_id=? AND ventana=?    # una particion
  validar_y_normalizar(filas)       # estado, UTC, referencias, dedupe por comentario_id
  agregados = agregar por (partido, minuto)
  cargar_idempotente(agregados, lote_id)   # reemplaza las filas (partido, minuto) del rango
  actualizar_checkpoint(ventana mas nueva cerrada, lote_id)
  registrar(lote_id, filas_leidas, descartadas por causa, duplicados, filas_cargadas)

cada 5 minutos: goles nuevos desde Neo4j -> FACT_GOL (clave evento_id, upsert)
una vez por dia: equipos desde MongoDB -> DIM_EQUIPO
```

| Aspecto | Decisión |
| :--- | :--- |
| Tipo | ETL por lotes incremental: se transforma y valida **antes** de cargar (Clase 13). |
| Frecuencia | Cada 5 minutos, cuando cierra una ventana de Cassandra. Lote final de cada partido 15 minutos después de terminado. |
| Retraso aceptable | Durante el partido, de 5 a 10 minutos: es un tablero de análisis, no el feed en vivo. El reporte postpartido es definitivo después del lote final. |
| Datos tardíos | Cada lote reprocesa las 2 ventanas anteriores a la marca (ventana de gracia). Lo que llegue después, lo corrige el lote final del partido. |
| Duplicados | Se deduplica por `comentario_id` en la transformación. La carga **reemplaza** las filas del rango procesado, así que repetir un lote no duplica. |
| Faltantes | Un minuto sin comentarios se carga con `n_comentarios = 0`, porque "no hubo comentarios" no es lo mismo que "no se cargó". Si falta `inicio_utc`, el partido queda fuera de la vista post-gol y se informa. |
| Falla parcial | El checkpoint solo avanza cuando el lote completo se cargó y validó. Si se corta a la mitad, el próximo lote repite el mismo rango, lo que es seguro porque la carga reemplaza. |
| Procedencia | Cada fila lleva `fuente`, `lote_carga` y `fecha_extraccion`. El registro de cada lote guarda el rango de ventanas, los conteos y los descartes por causa. |

## 7. Validación de conteos y agregados

- **Conteo contra la fuente**: para un partido y una ventana, la suma de `n_comentarios` de sus 5 minutos tiene que ser igual a la cantidad de `comentario_id` distintos visibles de esa partición en Cassandra. Es el mismo método que usa `validar_integridad.py` en este hito.
- **Goles contra el marcador**: la cantidad de filas de `FACT_GOL` por partido tiene que ser igual a `golesLocal + golesVisitante` del partido. Son dos datos independientes del grafo.
- **Rango**: `minuto_de_partido` entre 0 y aproximadamente 130, y conteos no negativos.
- **Referencias**: todo `partido_id` y `equipo_id` de los hechos existe en su dimensión. Los que no, se descartan y se cuentan.

## 8. Diferencia entre consultar las fuentes y consultar la proyección

| | Fuentes operacionales | Proyección analítica |
| :--- | :--- | :--- |
| Lecturas por reporte | Todas las particiones de todos los partidos, más el grafo y los documentos. | Una tabla agregada con unas 130 filas por partido. |
| Impacto en el camino operacional | Compite con el feed en vivo. | Ninguno al consultar. La extracción es por partición, acotada y periódica. |
| Frescura | Inmediata. | Entre 5 y 10 minutos durante el partido, y definitiva después del lote final. |
| Exactitud | Incluye duplicados por reintento. | Deduplicada, con la regla documentada. |
| Costo | Ninguno adicional, pero cada consulta es cara. | Almacenamiento, un proceso más que operar y reglas que mantener. |
| Procedencia | Implícita. | Explícita por fila y por lote. |

Dónde guardarla: el modelo dimensional, con uniones y consultas ad hoc por fase, equipo o partido, se adapta bien a una estructura relacional. Ver `comparacion_relacional.md`.
