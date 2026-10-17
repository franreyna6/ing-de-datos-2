# Problema temporal y patrones de acceso

Este documento se escribió **antes** de definir tablas, tags, fields, timestamps o políticas de conservación (RF2). El modelo de [`modelo_multidimensional.md`](modelo_multidimensional.md) se deriva de aquí.

## 1. Problema temporal

Durante cada partido del Mundial 2030 la plataforma recibe observaciones que cambian de forma continua. Se agrupan en cuatro fenómenos:

| Fenómeno | Fuente (simulada en el laboratorio) | Frecuencia de llegada | Para qué se necesita |
| :--- | :--- | :--- | :--- |
| Estadísticas de equipo (posesión, pases, tiros, recuperaciones) | Proveedor de datos del partido | 1 observación por segundo y por equipo | Pantalla de partido y análisis posterior |
| Actividad de usuarios (conectados e interacciones) | Plataforma, agregada por región | 1 por segundo y por región | Capacidad y momentos de interés |
| Métricas operativas (latencia, solicitudes, errores) | Servicios de la plataforma | 1 por segundo y por servicio | Salud de la plataforma durante el partido |
| Estadísticas de jugador (velocidad, distancia) | Seguimiento de los titulares | 1 cada 5 segundos por jugador | Rendimiento físico |

**Decisiones que deben tomarse en tiempo real:** mostrar la evolución reciente de un partido, detectar un pico de usuarios o un servicio degradado mientras el partido sigue, y comparar a los dos equipos en la misma ventana. Todas piden *una ventana de tiempo acotada* para *uno o pocos contextos*, nunca el histórico completo.

**Volumen.** El volumen no es arbitrario: sale de los datos del Hito 5 (96 partidos de la fase de grupos, 64 equipos, 12 sedes, 192 participaciones) y de una captura de 100 minutos por partido (6.000 s, que cubre los 90 minutos reglamentarios, el entretiempo y un margen de descuento).

| Tabla | Cuenta por partido | Puntos por partido | Puntos con 96 partidos |
| :--- | :--- | ---: | ---: |
| `estadisticas_equipo` | 2 equipos × 6.000 s | 12.000 | 1.152.000 |
| `actividad_usuarios` | 6 regiones × 6.000 s | 36.000 | 3.456.000 |
| `metricas_plataforma` | 6 servicios × 6.000 s | 36.000 | 3.456.000 |
| `estadisticas_jugador` | 22 titulares × 1.200 muestras (cada 5 s) | 26.400 | 2.534.400 |
| **Total** | | **110.400** | **10.598.400** |

El objetivo de 10M+ puntos se alcanza con la fase de grupos del Hito 5. El generador lo reproduce con `generacion_puntos.py --perfil completo` y el conteo se verificó sin escribir archivos (`--solo-contar`).

**Dato clave para el diseño:** en vivo, un partido genera unos **18,4 puntos por segundo** (2 + 6 + 6 + 22/5). La ingesta en tiempo real es modesta; lo que crece es la **acumulación** (10,6 M de puntos en 96 partidos) y el costo de **consultarla**. Por eso el diseño pone el esfuerzo en cardinalidad, rangos acotados y retención, y trata el 10M+ como una carga masiva (relleno) y no como una tasa de llegada.

## 2. Patrones de acceso

Cada patrón declara los siete aspectos pedidos por el enunciado (5.2). "Respuesta esperada" cubre ausencia de puntos, retraso de la fuente y dato tardío.

### PA1 — Evolución de las estadísticas de un equipo en un partido

| Aspecto | Declaración |
| :--- | :--- |
| Quién | La app y la web del Fixture (lectura); el proveedor de estadísticas (escritura) |
| Rango temporal | Últimos 5 a 15 minutos en vivo; el partido completo en la revisión posterior |
| Dimensiones | `partido_id`, `equipo_id` |
| Medidas | `posesion_pct`, `pases_acum`, `tiros_acum`, `recuperaciones_acum` |
| Frecuencia de llegada | 1 punto por segundo por equipo |
| Precisión temporal | Segundos |
| Ausencia / retraso / tardío | Sin puntos en la ventana: se muestra "sin datos" y se conserva el último valor conocido. Retraso de la fuente: los segundos faltantes quedan sin fila, no se rellenan. Dato tardío: se acepta, y la consulta lo devuelve en su posición temporal porque se ordena por `time` |
| Operaciones | Consultas C1, C2, C4 y agregaciones A1, A2, A3 |

### PA2 — Actividad de usuarios por región durante un partido

| Aspecto | Declaración |
| :--- | :--- |
| Quién | Operaciones y producto (lectura); la plataforma (escritura) |
| Rango temporal | El partido (100 minutos) y ventanas de minutos alrededor de un gol |
| Dimensiones | `partido_id`, `region` |
| Medidas | `usuarios_conectados` (estado medido), `interacciones` (conteo por segundo) |
| Frecuencia de llegada | 1 punto por segundo por región |
| Precisión temporal | Segundos |
| Ausencia / retraso / tardío | Sin puntos: no se infiere carga cero, se informa falta de datos. Un segundo faltante no se interpola. Dato tardío: se acepta y se ordena por tiempo |
| Operaciones | C5 y agregaciones A4, A5 |

### PA3 — Comparación entre partidos, sedes y grupos

| Aspecto | Declaración |
| :--- | :--- |
| Quién | Analistas de la competencia y ediciones del Fixture |
| Rango temporal | Una jornada o el periodo del torneo (13 al 30 de junio de 2030), siempre acotado |
| Dimensiones | `sede`, `grupo`, `partido_id`, `equipo_id` |
| Medidas | Valores finales de `tiros_acum`, `pases_acum`, `recuperaciones_acum` |
| Frecuencia de llegada | Lectura de baja frecuencia sobre datos ya cargados |
| Precisión temporal | Segundos (el dato original); el resumen de 1 minuto sirve para el histórico |
| Ausencia / retraso / tardío | Un partido sin datos no aparece en el ranking. Un dato tardío puede cambiar el valor final de un contador, por lo que los comparativos se recalculan al consultar |
| Operaciones | C3 y agregación A7 |

### PA4 — Salud operativa de la plataforma durante un partido

| Aspecto | Declaración |
| :--- | :--- |
| Quién | El equipo de plataforma (lectura); los servicios (escritura) |
| Rango temporal | La ventana del partido |
| Dimensiones | `partido_id`, `servicio` |
| Medidas | `latencia_ms`, `solicitudes`, `errores` |
| Frecuencia de llegada | 1 punto por segundo por servicio |
| Precisión temporal | Segundos |
| Ausencia / retraso / tardío | La falta de puntos de un servicio es en sí una señal (servicio mudo) y se distingue de "latencia cero". Dato tardío: se acepta |
| Operaciones | C6 y agregación A6 |

### PA5 — Rendimiento físico de los titulares

| Aspecto | Declaración |
| :--- | :--- |
| Quién | Cuerpo técnico y medios (lectura); el seguimiento de jugadores (escritura) |
| Rango temporal | El partido |
| Dimensiones | `partido_id`, `equipo_id`, `jugador_id` |
| Medidas | `velocidad_kmh` (muestra), `distancia_acum_m` (contador) |
| Frecuencia de llegada | 1 punto cada 5 segundos por jugador |
| Precisión temporal | Segundos |
| Ausencia / retraso / tardío | Un jugador sin datos (por ejemplo, por un cambio) no se rellena. Se asume 11 titulares fijos y sin sustituciones; es una simplificación declarada |
| Operaciones | C7 |

### PA6 — Conservación histórica de las estadísticas

| Aspecto | Declaración |
| :--- | :--- |
| Quién | Análisis posterior al torneo |
| Rango temporal | Todo el torneo |
| Dimensiones | `partido_id`, `equipo_id`, `sede`, `grupo` |
| Medidas | Posesión promedio y valores de cierre de los contadores, por minuto |
| Frecuencia de llegada | Una vez, al terminar cada partido (resumen derivado) |
| Precisión temporal | Segundos, alineados al inicio de cada minuto |
| Ausencia / retraso / tardío | Si llega un dato tardío antes de que expire el original, el resumen se puede recalcular y reemplaza al anterior (misma serie y mismo timestamp) |
| Operaciones | Resumen R1 de `agregaciones.py` |

## 3. De los patrones al modelo

| Pregunta que se repite en los patrones | Decisión de modelo |
| :--- | :--- |
| "Por partido" y "por equipo" aparecen en casi todos | `partido_id` y `equipo_id` son tags |
| "Por región" y "por servicio" son filtros y comparaciones | `region` y `servicio` son tags en su tabla |
| "Por sede" y "por grupo" se usan en comparativos (PA3) | `sede` y `grupo` son tags de `estadisticas_equipo` |
| Los valores se agregan, comparan o grafican | Las medidas son fields |
| Nadie pide "el punto con este identificador" | No hay identificador por punto, ni como tag ni como field |

La justificación completa está en [`modelo_multidimensional.md`](modelo_multidimensional.md) y [`cardinalidad_y_escalabilidad.md`](cardinalidad_y_escalabilidad.md).
