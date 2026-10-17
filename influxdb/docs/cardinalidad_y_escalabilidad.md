# Cardinalidad, carga y escalabilidad

## 1. Cardinalidad

La cardinalidad de series es la cantidad de combinaciones únicas de tabla y tags. Cada serie suma a índice y memoria, por lo que el modelo debe acotarla (RF11, RNF5).

### Variación de cada dimensión

| Dimensión | Valores posibles | Fuente de la cifra | Tablas donde es tag |
| :--- | ---: | :--- | :--- |
| `partido_id` | 96 | `partidos.csv` (Hito 5) | las cuatro |
| `equipo_id` | 64 | `equipos.csv` | `estadisticas_equipo`, `estadisticas_jugador` |
| `sede` | 12 | `sedes.csv` | `estadisticas_equipo` |
| `grupo` | 12 | `partidos.csv` (grupos A a L) | `estadisticas_equipo` |
| `region` | 6 | definida por el módulo | `actividad_usuarios` |
| `servicio` | 6 | definida por el módulo | `metricas_plataforma` |
| `jugador_id` | 1.024 | `jugadores.csv` (11 titulares por equipo en cada partido) | `estadisticas_jugador` |

### Estimación de series por tabla

Una serie existe solo si esa combinación se da en la realidad. Un equipo juega un número acotado de partidos, y cada partido tiene una sola sede y un solo grupo.

| Tabla | Combinaciones **potenciales** (producto de dimensiones) | Series **reales** (96 partidos) | Cómo se obtiene |
| :--- | ---: | ---: | :--- |
| `estadisticas_equipo` | 96 × 64 × 12 × 12 = 884.736 | **192** | 96 partidos × 2 equipos (coincide con las 192 filas de `participaciones.csv`) |
| `actividad_usuarios` | 96 × 6 = 576 | **576** | 96 partidos × 6 regiones |
| `metricas_plataforma` | 96 × 6 = 576 | **576** | 96 partidos × 6 servicios |
| `estadisticas_jugador` | 96 × 64 × 1.024 = 6.291.456 | **2.112** | 96 partidos × 22 titulares |
| **Total** | | **3.456** | |

La brecha entre lo potencial y lo real es el argumento central: `sede` y `grupo` **no multiplican** las series de `estadisticas_equipo` porque están determinados por el partido, y `equipo_id` en `estadisticas_jugador` queda determinado por el jugador. El script de validación (V4) cuenta las series realmente cargadas y las compara con esta estimación.

Para el perfil local (12 partidos) la estimación es 24 + 72 + 72 + 264 = **432 series**.

### Puntos por serie

El total de 10.598.400 puntos reparte unos 3.067 puntos por serie en promedio (10.598.400 / 3.456). Series largas y poco numerosas es la forma saludable en una base temporal: pocas entradas de índice y mucho dato por entrada.

### Atributos descartados como tag y qué habría pasado

| Atributo candidato | Si fuera tag | Decisión |
| :--- | :--- | :--- |
| Identificador único por punto | Series ≈ puntos: hasta 10.598.400 series en lugar de 3.456 | No se registra |
| `usuario_id` | Del orden de la cantidad de usuarios del escenario (millones simultáneos según el Hito 2) por partido | No se registra. La actividad por usuario es de Redis (Hito 7); acá solo se guarda el total por región |
| Valor de una medida (por ejemplo, el valor de posesión) | Una serie por cada valor distinto | Es field |
| Timestamp | Una serie por segundo | Es la columna `time` |
| Texto libre | Una serie por texto distinto | Pertenece a Cassandra (Hito 6) |
| `minuto_de_juego` | Redundante con `time` y con el inicio del partido | Se obtiene con `date_trunc` al consultar |

**Riesgo vigilado:** `jugador_id` es la dimensión más variable (2.112 series). Se acepta porque PA5 consulta por jugador, está acotada por las plantillas (11 titulares × 2 equipos × 96 partidos) y no crece con el tiempo. Si en el futuro se agregaran suplentes o más muestras por jugador, se revisaría: sumar los 16 jugadores por equipo daría 3.072 series; el costo pasa por la cantidad de series, no por la frecuencia de muestreo.

## 2. Carga de datos

### Estrategia para el objetivo de 10M+ puntos (RF12)

| Aspecto | Decisión | Fundamento |
| :--- | :--- | :--- |
| Generación | `generacion_puntos.py`, determinística (semilla 2030), escribe line protocol en `data/generado/<perfil>/` y un `manifest.json` con los totales esperados | Separa generación, carga y validación (RF7). Con la misma semilla el resultado es idéntico |
| Volumen | `muestra` 22.080, `local` 1.324.800, `completo` 10.598.400 puntos | Ver `patrones_de_acceso.md`, sección 1 |
| Tamaño de archivos | `local`: 156 MB medidos (≈ 123,5 bytes por línea). `completo`: ≈ 1,25 GB, estimado por proporción (8 veces `local`) | Hay que tener ese espacio libre antes de generar `completo` |
| Timestamps | `inicio del partido + t` en segundos, ordenados en el tiempo dentro de cada tabla | Reproducible y sin depender del reloj de la máquina |
| Precisión | Segundos, declarada al escribir (`precision=second`) | Ver `modelo_multidimensional.md` |
| Tamaño de lote | **5.000 líneas** por defecto (unos 0,6 MB); configurable con `--tamano-lote` | Un punto por solicitud agrega overhead; un lote enorme consume memoria y complica los reintentos. El valor por defecto es un punto de partida que **se mide** con `--medir-lotes` (500, 5.000 y 20.000) |
| Concurrencia | **4 hilos**, una conexión persistente por hilo, con cola acotada de lotes en vuelo (2 por hilo); configurable con `--concurrencia` | Superpone red y escritura sin acumular lotes en memoria. También se mide (1 y 4 hilos) |
| Orden y desorden | La carga normal va en orden temporal. `--desorden` baraja las líneas dentro de cada lote; la validación V9 muestra que el orden de llegada no altera el resultado | InfluxDB ordena por tiempo; un dato tardío es válido |
| Reintentos | Hasta 5, con espera exponencial (0,5 s, 1 s, 2 s...), **solo** ante errores transitorios: fallo de conexión, HTTP 429 y 5xx | Un reintento es seguro: reescribir el mismo punto lo reemplaza (V8 lo comprueba) |
| Errores permanentes | Un 4xx (conflicto de tipos, line protocol inválido) **no se reintenta**: el lote se guarda en `rechazados.lp`, se cuenta y el script termina con código 1 | Reintentar un error de datos nunca lo corrige. El servidor informa `partial write of line protocol occurred`: puede haber escrito las líneas válidas del lote y rechazado solo las inválidas. El script guarda el lote entero por prudencia; reenviarlo no duplica nada porque reescribir un punto lo reemplaza (V8) |
| Validación | `validacion.py` compara InfluxDB con el `manifest.json`: puntos por tabla, por partido, series y rango temporal | Si la carga pierde o duplica algo, se ve |

### Cantidad de solicitudes del objetivo

| Tamaño de lote | Solicitudes para 10.598.400 puntos |
| ---: | ---: |
| 500 | 21.197 |
| 5.000 | 2.120 |
| 20.000 | 530 |

**Tiempo de carga proyectado.** No se declara un número: se calcula como `10.598.400 / puntos por segundo observados`, con la tasa medida en el laboratorio (ver `pruebas_y_evidencia.md`). Una proyección lineal desde un subconjunto es una estimación, no una medición del volumen completo.

### Prueba local efectivamente realizada frente al objetivo

| | Objetivo de diseño | Prueba local |
| :--- | :--- | :--- |
| Puntos | 10.598.400 (`completo`) | Los del perfil ejecutado (por defecto `local`: 1.324.800) |
| Cómo se afirma | Conteo del generador (`--solo-contar`) y estimación | Conteo verificado en InfluxDB por `validacion.py` |
| Qué se puede decir | Que el modelo y la estrategia están dimensionados para ese volumen | Lo medido, con método, ambiente y datos cargados |

## 3. Escalabilidad

### Límites de InfluxDB 3 Core que afectan al diseño

Según la documentación de configuración de Core (consultada al preparar la entrega):

| Opción | Valor por defecto | Efecto en este módulo |
| :--- | :--- | :--- |
| `query-file-limit` | 432 archivos Parquet por consulta; si se supera, el servidor devuelve error | Los datos se organizan en bloques de 10 minutos por tabla (`gen1-duration`). Un partido de 100 minutos son 10 bloques por tabla. Una consulta que recorre todos los partidos de una tabla toca unos **120 archivos con el perfil `local`** (12 partidos × 10) y unos **960 con `completo`** (96 × 10), más si el servidor escribió más de un archivo por bloque. Es una estimación, no una medición. Por eso las consultas de periodo largo (A7, el resumen R1, los conteos de la validación) pueden fallar con `completo`; el compose permite subir el límite con `INFLUXDB3_QUERY_FILE_LIMIT` |
| `wal-flush-interval` | 1 s | Probablemente cada escritura se confirma tras el volcado del WAL; con lotes chicos el tiempo lo domina esa espera y no la cantidad de puntos. Es una hipótesis que la tabla de `--medir-lotes` permite contrastar |
| `wal-files-per-snapshot` | 600 | Cada 600 archivos de WAL el servidor persiste datos como Parquet; por eso los datos viven en memoria y en disco a la vez durante la carga |

### Límites del laboratorio

- **Un solo nodo** de InfluxDB 3 Core en Docker, con los recursos que asigne Docker Desktop (se registran en el log de cada corrida).
- **Un cliente Python**: la tasa de carga medida es la del conjunto cliente más servidor en una máquina, y el cliente puede ser el límite.
- **Una sola máquina** para todo: no se mide la red ni el efecto de varias cargas simultáneas.
- **Datos simulados** con una semilla fija: la forma de las series es plausible pero no proviene de una fuente real.

### Crecimiento esperado (cálculo, no medición)

| Escenario | Cálculo | Puntos |
| :--- | :--- | ---: |
| Fase de grupos del Hito 5 | 96 × 110.400 | 10.598.400 |
| Torneo de 127 partidos (escenario del enunciado) | 127 × 110.400 | 14.020.800 |
| Muestreo de equipos, usuarios y servicios a 2 por segundo | 96 × ((12.000 + 36.000 + 36.000) × 2 + 26.400) | 18.662.400 |
| Los 16 jugadores de cada plantilla en vez de 11 titulares | 96 × (84.000 + 32 × 1.200) | 11.750.400 |

La cantidad de **series** crece con partidos, equipos y jugadores, no con el muestreo: duplicar la frecuencia duplica los puntos pero deja las series intactas.

### Qué cambiaría al crecer

| Cambio | Efecto | Respuesta dentro de lo visto en clase |
| :--- | :--- | :--- |
| Más puntos por segundo | Más solicitudes de escritura | Ajustar lote y concurrencia con la medición de `--medir-lotes` |
| Más dimensiones | Series multiplicadas | Repetir el análisis de esta sección antes de agregar un tag |
| Más fuentes (otras regiones, otros servicios) | Más valores de `region` y `servicio` | La estimación crece linealmente por partido; revisar V4 |
| Consultas sobre periodos largos | Más datos leídos | Consultar el resumen de 1 minuto en vez del dato original |
| Más datos históricos | Más almacenamiento | Retención del dato original y resumen (ver `retencion_y_granularidad.md`) |

La distribución en varios nodos y el monitoreo de producción **no se tratan** en este hito: el alcance declarado es captura, consulta, agregación, cardinalidad, retención y carga en un nodo local.
