# Carga, consultas y agregaciones

## 1. Flujo en tres etapas separadas (RF7, RNF9)

| Etapa | Script | Entrada | Salida |
| :--- | :--- | :--- | :--- |
| Generación | `generacion_puntos.py` | `data/origen/*.csv` (Hito 5) | `data/generado/<perfil>/*.lp` y `manifest.json` |
| Carga | `carga_lotes.py` | Los archivos `.lp` | Puntos en `fixture2030_vivo` (por `POST /api/v3/write_lp`, `precision=second`) |
| Validación | `validacion.py` | InfluxDB y `manifest.json` | PASS, FAIL o INFO por verificación |

La inicialización (compose, token, bases) está aparte en `inicializacion.py`, y la ejecución encadenada en `ejecutar_todo.ps1` / `ejecutar_todo.sh`, que dejan el log en `docs/evidencia/logs/`.

Estrategia de lote, concurrencia, reintentos y errores: ver `cardinalidad_y_escalabilidad.md`, sección 2.

## 2. Consultas temporales (`scripts/sql/consultas_temporales.sql`)

Todas acotan rango temporal y dimensiones (RNF8). El partido de referencia es **F2030-018** (Túnez local contra Argelia, grupo C, sede CAMP, inicio 2030-06-13 08:00 UTC), el primero del calendario y el primero que incluye cualquier perfil.

| ID | Qué hace | Patrón | Qué se espera ver |
| :--- | :--- | :--- | :--- |
| C1 | 10 puntos consecutivos de un equipo en el minuto 60 | PA1 | Una fila por segundo con las cuatro medidas; los contadores no bajan |
| C2 | Cuenta de puntos de la ventana de los minutos 60 a 75 | PA1 | 15 min × 60 s = **900 puntos por equipo** si no hubo huecos |
| C3 | Valores finales de contadores filtrando por `sede` y `grupo` en una jornada | PA3 | Una fila por equipo-partido de esa sede y grupo |
| C4 | Posesión promedio por minuto de los dos equipos | PA1 / PA3 | Dos filas por minuto que suman ≈ 100 |
| C5 | Pico, promedio e interacciones por región | PA2 | El pico de cada región es mayor que su promedio |
| C6 | Latencia, solicitudes y errores por servicio | PA4 | Una fila por servicio |
| C7 | Los 5 titulares con más distancia recorrida | PA5 | Cinco filas con distancia y velocidad máxima |

**Cada consulta incluye `ORDER BY`, ventana `[inicio, fin)` y filtro por `partido_id`**, salvo C3 (que filtra por `sede`, `grupo` y una jornada) y A7 (que recorre el periodo del torneo, acotado entre el 1 de junio y el 15 de julio de 2030).

## 3. Agregaciones (`scripts/sql/agregaciones.sql` y `agregaciones.py`)

Cada bloque declara la función elegida y **la semántica de la medida** que la justifica (RF9).

| ID | Operación | Función | Por qué esa función |
| :--- | :--- | :--- | :--- |
| A1 | Posesión por ventanas de 5 minutos | `AVG` con `date_bin` | La posesión es una muestra instantánea |
| A2 | Tiros finales: forma correcta frente a incorrecta | `MAX` frente a `SUM` | `tiros_acum` ya es un total; sumarlo cuenta cada tiro cientos de veces. La consulta muestra los dos resultados |
| A3 | Tiros acumulados al cierre de cada tramo de 15 minutos | `MAX` con `date_bin` | Un contador se resume por su valor al cierre; los tiros del tramo salen restando el tramo anterior |
| A4 | Pico de usuarios simultáneos totales | `SUM` por instante y luego orden descendente | Se suma entre regiones **en el mismo segundo** y se toma el máximo: el pico es un extremo |
| A5 | Minutos de mayor interacción | `SUM` con `date_trunc` | `interacciones` es un conteo por segundo |
| A6 | Errores por millón de solicitudes | `SUM` / `SUM` | Se suman por separado antes de dividir; promediar tasas por segundo distorsiona el total |
| A7 | Partidos con más tiros totales | `MAX` por equipo y luego `SUM` | El valor final por equipo es el máximo; el total del partido suma los dos equipos |
| R1 | Resumen de 1 minuto hacia `fixture2030_hist` | `AVG`, `MAX`, `COUNT` | Ver `retencion_y_granularidad.md` |

**Sobre las funciones de ventana.** Las agregaciones por ventana (`date_trunc('minute', time)` y `date_bin(INTERVAL '5 minutes', time)`) implementan lo visto en clase sobre ventanas temporales: la Clase 9 explica el concepto ("promedio por minuto", ventanas de 1 y 5 minutos) y muestra `AVG`, `SUM`, `MAX` y `GROUP BY`, pero no incluye la sintaxis de la función de ventana. Se usaron `date_trunc` y `date_bin` por ser las funciones SQL que agrupan por ventanas de ancho fijo. Es el único elemento de sintaxis que va más allá de los ejemplos literales de la clase.

## 4. Interpretación y límites

La interpretación de un resultado depende del contexto del partido; estas son las lecturas correctas y sus límites.

| Consulta | Cómo interpretarla | Límite |
| :--- | :--- | :--- |
| C1, C2 | Muestran la evolución local y la densidad de captura | Una ventana con menos de 900 puntos indica un hueco, no carga cero |
| C4, A1 | La suma de ambos equipos ≈ 100 es una propiedad **del generador** (la posesión del visitante es 100 menos la del local); no es una conclusión sobre el juego | Con datos reales de un proveedor habría que validar esa suma |
| C5, A4 | El pico mide capacidad máxima observada; el promedio, carga sostenida | Un promedio no reemplaza al pico ni explica causalidad |
| A5 | Los minutos de mayor interacción se comparan con los minutos de gol de `eventos.csv` (Hito 5): el generador sube la interacción después de cada gol | Es una relación **construida** en la simulación, y la validación V11 la verifica; no demuestra un comportamiento real de la audiencia |
| C6, A6 | Comparan servicios dentro del partido | Los valores salen de parámetros del generador; no representan los servicios reales |
| C7 | Distancias y velocidades de titulares | Se asume 11 titulares fijos y sin sustituciones |
| A2 | La columna incorrecta existe para mostrar el error, no para usarse | |
| A7 | Compara solo los partidos cargados; con el perfil `local` son 12 de 96 | |

**Tiempos.** Cada consulta imprime el tiempo de **una** ejecución, incluida la red local. Es un dato de orientación y **no** una medición de rendimiento: no hay repeticiones, percentiles ni control de caché.
