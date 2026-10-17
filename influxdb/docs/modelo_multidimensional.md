# Modelo multidimensional

El modelo distingue de forma explícita **tabla, tags, fields, timestamp y serie** (InfluxDB 3 Core, escritura por line protocol). Cada elemento responde a un patrón de [`patrones_de_acceso.md`](patrones_de_acceso.md) (RNF4).

- **Tabla:** el fenómeno que se registra.
- **Tag:** metadato de texto que forma parte de la identidad de la serie y se usa para filtrar y agrupar.
- **Field:** valor observado (entero, flotante, booleano o texto).
- **Timestamp:** instante de la observación, con precisión declarada.
- **Serie:** el conjunto de puntos que comparten tabla y combinación de tags.

**Precisión temporal (RF6, RNF6): segundos, en todo el módulo.** La captura es de 1 observación por segundo (1 cada 5 s para jugadores), así que el segundo es la unidad natural: una precisión mayor (milisegundos o nanosegundos) solo agregaría dígitos sin información. Se declara al escribir con `precision=second` y se usa el mismo valor en el generador, el cargador y las consultas. Consecuencia que se tiene en cuenta: dos puntos de la **misma serie y el mismo segundo** son el mismo punto, y el último escrito reemplaza al anterior. El generador produce como máximo un punto por serie y por segundo.

Los timestamps se generan de forma determinística: `inicio del partido + t` segundos, donde el inicio sale de la fecha de `partidos.csv` y de un horario por orden dentro del día (08, 11, 14, 17, 20 y 23 UTC), con 3 horas entre partidos.

## Tablas

### `estadisticas_equipo`

| | |
| :--- | :--- |
| Fenómeno | Estado estadístico de un equipo durante un partido |
| Tags | `partido_id`, `equipo_id`, `sede`, `grupo` |
| Fields | `posesion_pct` (float), `pases_acum` (entero), `tiros_acum` (entero), `recuperaciones_acum` (entero) |
| Timestamp | Segundo de captura; fuente: reloj del generador anclado al inicio del partido |
| Serie | `(partido_id, equipo_id)`; `sede` y `grupo` quedan determinados por el partido |
| Patrones | PA1, PA3, PA6 |

`sede` y `grupo` son **tags dependientes**: una vez conocido el `partido_id`, su valor queda fijado, así que no multiplican las series. Se mantienen como tags porque PA3 filtra por ellos y así la consulta no necesita conocer los partidos de antemano.

### `actividad_usuarios`

| | |
| :--- | :--- |
| Fenómeno | Presencia y participación de la audiencia por región |
| Tags | `partido_id`, `region` |
| Fields | `usuarios_conectados` (entero), `interacciones` (entero) |
| Timestamp | Segundo de captura |
| Serie | `(partido_id, region)` |
| Patrones | PA2 |

La región es una agregación geográfica de la plataforma; **no** se registra a los usuarios individuales.

### `metricas_plataforma`

| | |
| :--- | :--- |
| Fenómeno | Salud operativa de los servicios mientras se juega el partido |
| Tags | `partido_id`, `servicio` |
| Fields | `latencia_ms` (float), `solicitudes` (entero), `errores` (entero) |
| Timestamp | Segundo de captura |
| Serie | `(partido_id, servicio)` |
| Patrones | PA4 |

### `estadisticas_jugador`

| | |
| :--- | :--- |
| Fenómeno | Rendimiento físico de los 11 titulares de cada equipo |
| Tags | `partido_id`, `equipo_id`, `jugador_id` |
| Fields | `velocidad_kmh` (float), `distancia_acum_m` (float) |
| Timestamp | Cada 5 segundos |
| Serie | `(partido_id, equipo_id, jugador_id)`; `equipo_id` queda determinado por el jugador |
| Patrones | PA5 |

Los titulares se eligen de `jugadores.csv` (1 arquero, 4 defensores, 4 mediocampistas y 2 delanteros, por dorsal ascendente).

### `estadisticas_equipo_1m` (base `fixture2030_hist`)

Tabla **derivada**, resumen de 1 minuto de `estadisticas_equipo` (ver [`retencion_y_granularidad.md`](retencion_y_granularidad.md)). Tags: `partido_id`, `equipo_id`, `sede`, `grupo`. Fields: `posesion_pct_prom` (float), `pases_acum_max`, `tiros_acum_max`, `recuperaciones_acum_max` y `muestras` (enteros). El timestamp es el inicio del minuto.

## Medidas: tipo, semántica y agregación correcta (RF5)

La función de agregación depende de **qué significa cada punto**, no del tipo de dato. El módulo registra medidas de cuatro naturalezas distintas:

| Naturaleza | Medidas | Tipo | Agregación correcta | Agregación incorrecta y por qué |
| :--- | :--- | :--- | :--- | :--- |
| Muestra instantánea | `posesion_pct`, `velocidad_kmh`, `latencia_ms` | float | `AVG` para la tendencia; `MAX` o `MIN` para extremos | `SUM`: sumar porcentajes o velocidades no tiene significado |
| Estado medido (nivel) | `usuarios_conectados` | entero | `MAX` para el pico, `AVG` para la carga sostenida | `SUM` en el tiempo: contaría a los mismos usuarios en cada segundo. La suma entre regiones solo vale **en el mismo instante** (consulta A4) |
| Contador acumulado | `pases_acum`, `tiros_acum`, `recuperaciones_acum`, `distancia_acum_m` | entero / float | `MAX` en la ventana (valor al cierre); la actividad de un tramo es la diferencia entre cierres | `SUM`: repite cada tiro tantas veces como lecturas haya. La consulta A2 muestra ambos resultados lado a lado |
| Conteo por intervalo | `interacciones`, `solicitudes`, `errores` | entero | `SUM` por ventana | `AVG` de tasas por segundo distorsiona el total; las tasas compuestas (errores por millón) se calculan como `SUM` / `SUM` (A6) |

**Tipos consistentes (RNF6).** Una vez escrito un field con un tipo, InfluxDB lo fija para esa tabla y rechaza un tipo distinto. Por eso los enteros llevan sufijo `i` (`pases_acum=12i`) y los flotantes se escriben siempre con decimal (`posesion_pct=50.0`). La validación V10 comprueba el comportamiento observado ante un conflicto.

## Relación entre modelo y operaciones (RNF4)

| Elemento | Operación que lo justifica |
| :--- | :--- |
| Tag `partido_id` | Todas las consultas filtran por partido (C1 a C7, A1 a A6) |
| Tag `equipo_id` | Comparar los dos equipos de un partido (C1, C4) |
| Tags `sede` y `grupo` | Filtro de contexto de PA3 (C3) |
| Tag `region` | Comparar regiones (C5) |
| Tag `servicio` | Comparar servicios (C6, A6) |
| Tag `jugador_id` | Ranking de titulares (C7) |
| Fields acumulados | Valores finales y tramos (A2, A3, A7) |
| Fields de conteo | Sumas por minuto o por servicio (A5, A6) |
| Fields de muestra | Promedios por ventana (A1, C4) |
| Precisión en segundos | Ventanas de 1, 5 y 15 minutos (`date_trunc`, `date_bin`) |
| Tabla derivada de 1 minuto | PA6, conservación histórica |

## Atributos que no son tags

| Atributo | Decisión | Razón |
| :--- | :--- | :--- |
| Identificador único por punto o por evento | No existe | Ningún patrón busca un punto por identificador; como tag, cada punto sería una serie |
| Identificador de usuario o de sesión | No se registra | Habría millones de valores; la actividad por usuario pertenece al modelo de sesiones (Hito 7) |
| Texto libre (comentarios) | No se registra | Pertenece al módulo de comentarios (Hito 6) |
| El valor de una medida | Es field | Varía en cada punto |
| El timestamp | Es la columna `time` | No se duplica como atributo |
| Nombre del equipo, de la sede o del jugador | No se guarda | Está en los datos de los hitos 4 y 5; el código basta para unir |

El análisis numérico de cardinalidad está en [`cardinalidad_y_escalabilidad.md`](cardinalidad_y_escalabilidad.md).
