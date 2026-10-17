# Retención, granularidad y ciclo de vida

Retención y downsampling no son un detalle de infraestructura: definen qué preguntas se podrán responder en el futuro y cuánto costará conservar la información (RF10).

## 1. Ciclo de vida de una observación

| Etapa | Qué ocurre | Dónde vive | Granularidad |
| :--- | :--- | :--- | :--- |
| 1. Captura en vivo | La observación llega durante el partido | `fixture2030_vivo` | 1 s (jugadores: 5 s) |
| 2. Consulta en vivo | La pantalla de partido pide los últimos minutos | `fixture2030_vivo` | 1 s |
| 3. Revisión posterior | Análisis del partido y comparación entre partidos | `fixture2030_vivo` | 1 s |
| 4. Resumen | Al terminar el partido se deriva el resumen de 1 minuto | `fixture2030_hist` | 1 min |
| 5. Expiración | El dato original sale de `fixture2030_vivo` al cumplirse su retención | (desaparece) | — |
| 6. Histórico | Solo queda el resumen | `fixture2030_hist` | 1 min |

## 2. Política declarada

| Base | Retención | Qué guarda | Por qué |
| :--- | :--- | :--- | :--- |
| `fixture2030_vivo` | **30 días** | Los puntos originales de las cuatro tablas | La precisión de 1 segundo hace falta durante el partido (PA1, PA2, PA4, PA5) y en la revisión posterior, que incluye correcciones del proveedor y comparaciones entre partidos (PA3). Pasado ese mes, el detalle por segundo deja de responder preguntas que alguien vaya a hacer |
| `fixture2030_hist` | **Sin expiración** | Resúmenes de 1 minuto | El valor histórico está en la tendencia y en los valores de cierre, no en cada segundo (PA6) |
| `fixture2030_lab` | Sin expiración | Pruebas descartables | Solo para lotes, dato tardío y conflicto de tipos; se puede borrar |

**La retención se fija al crear la base.** En InfluxDB 3 Core el período de retención se establece cuando se crea la base de datos y no se modifica después (visto en la Clase 9). `inicializacion.py` crea `fixture2030_vivo` con `--retention-period 30d`. Por eso la decisión se tomó con criterio conservador antes de cargar: cambiarla exigiría crear otra base y volver a cargar los datos.

**Qué se puede y qué no se afirma de este laboratorio.** Los timestamps de los datos son de junio de 2030, es decir, **posteriores** a la fecha de ejecución. La retención se mide contra el tiempo actual, así que en el laboratorio **no expira nada** y no se demuestra la expiración. Lo que queda registrado es el parámetro con que `inicializacion.py` crea cada base (`--retention-period 30d` para `fixture2030_vivo`); en la salida observada `influxdb3 show databases` lista solo los nombres, así que el log no es una confirmación del servidor sobre el período aplicado. La expiración real se observaría en el torneo, 30 días después de cada partido.

## 3. Agregación según la semántica de cada medida

Resumir no es promediar todo. La función del resumen depende de qué significa el punto (ver `modelo_multidimensional.md`).

| Tabla | Medida | Función en el resumen de 1 minuto | Qué se pierde |
| :--- | :--- | :--- | :--- |
| `estadisticas_equipo` | `posesion_pct` | `AVG` | Las oscilaciones dentro del minuto |
| `estadisticas_equipo` | `pases_acum`, `tiros_acum`, `recuperaciones_acum` | `MAX` (valor al cierre del minuto) | En qué segundo ocurrió cada evento dentro del minuto |
| `estadisticas_equipo` | cantidad de puntos | `COUNT(*)` (`muestras`) | Nada: sirve para comprobar que el resumen cubre los puntos originales |
| `actividad_usuarios` | `usuarios_conectados` | `AVG` **y** `MAX` | Un promedio solo escondería el pico; por eso se conservan ambos |
| `actividad_usuarios` | `interacciones` | `SUM` | El segundo exacto de cada interacción |
| `metricas_plataforma` | `latencia_ms` | `AVG` **y** `MAX` | Con solo el promedio se pierden los picos de latencia |
| `metricas_plataforma` | `solicitudes`, `errores` | `SUM` | El segundo exacto |
| `estadisticas_jugador` | `velocidad_kmh` | `AVG` y `MAX` | La secuencia de velocidades |
| `estadisticas_jugador` | `distancia_acum_m` | `MAX` | El ritmo dentro del minuto |

**Alcance implementado.** El resumen **implementado** y ejecutado es el de `estadisticas_equipo` (script `agregaciones.py`, bloque R1, tabla `estadisticas_equipo_1m`). Las otras tres filas de la tabla están **diseñadas**, no implementadas: el resumen de las otras tablas sigue exactamente el mismo mecanismo.

## 4. Tamaño del resumen frente al original (estimación)

Estimación por cuenta, para 96 partidos y 100 minutos por partido:

| Tabla | Puntos originales | Puntos de resumen de 1 minuto | Reducción |
| :--- | ---: | ---: | ---: |
| `estadisticas_equipo` | 1.152.000 | 19.200 (192 series × 100 min) | 60 a 1 |
| `actividad_usuarios` | 3.456.000 | 57.600 (576 × 100) | 60 a 1 |
| `metricas_plataforma` | 3.456.000 | 57.600 (576 × 100) | 60 a 1 |
| `estadisticas_jugador` | 2.534.400 | 211.200 (2.112 × 100) | 12 a 1 |
| **Total** | **10.598.400** | **345.600** | **≈ 30 a 1** (el resumen es el 3,26 % del original) |

Son puntos, no bytes: el resumen tiene más fields por punto (por ejemplo, promedio y máximo), así que el ahorro en almacenamiento es algo menor que el ahorro en puntos. El script `agregaciones.py` comprueba que la suma de `muestras` del resumen coincide con los puntos originales.

## 5. Efecto de la política sobre cada necesidad

| Necesidad | Qué usa | Efecto de la política |
| :--- | :--- | :--- |
| Consulta en vivo | El dato original, con rango corto | Sin efecto: el dato está dentro de los 30 días |
| Revisión del partido | El dato original, con el partido completo | Disponible 30 días; después, solo en resolución de 1 minuto |
| Análisis histórico del torneo | El resumen de 1 minuto | Consultas más baratas y rápidas; no responde preguntas por segundo |
| Almacenamiento | El original expira; el resumen no | El volumen retenido crece con la cantidad de partidos del resumen y no con la cantidad de segundos |
| Costo de conservar | Resumen chico y sin límite de tiempo | Bajo; es el costo de lo que se decidió recordar para siempre |
| Pregunta nueva que exija el segundo | Ya expiró | **No se puede responder**: es el costo explícito de la decisión |

El downsampling reduce el detalle de una **representación derivada**; no reemplaza la decisión de expirar o conservar los puntos originales. Las dos decisiones se tomaron por separado: el resumen se crea y se conserva siempre, y el original expira a los 30 días.

## 6. Qué cambiaría si crecen las fuentes

- **Más partidos o más muestreo:** sube el volumen del dato original, no el del resumen por minuto. Se mantiene la retención y se revisa si 30 días siguen alcanzando.
- **Una nueva medida:** se define su naturaleza (muestra, contador, conteo, nivel) antes de elegir la función de resumen.
- **Preguntas por segundo después de 30 días:** exigirían ampliar la retención. Como en Core no se modifica, habría que crear una base nueva y volver a cargar.
