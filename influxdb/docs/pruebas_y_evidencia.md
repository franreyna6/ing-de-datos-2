# Pruebas y evidencia

## 1. Método

1. `ejecutar_todo.ps1` (Windows) o `ejecutar_todo.sh` (Linux/macOS) corre las seis etapas en orden: inicialización, generación, carga, consultas, agregaciones y validación. Cada ejecución escribe un log con fecha en `docs/evidencia/logs/ejecucion_<perfil>_<fecha>.log`.
2. El log registra, antes de cualquier resultado, lo que exige RNF10: **fecha de ejecución**, **versión de InfluxDB** (`influxdb3 --version` dentro del contenedor), **identificador de la imagen**, **recursos** (CPUs y memoria de Docker, más el equipo) y **volumen procesado**.
3. Opcionalmente, `-MedirLotes` (o `--medir-lotes`) compara tamaños de lote y concurrencias, y `-ProbarPersistencia` ejecuta `persistencia.py`: cuenta los puntos de cada tabla, reinicia el contenedor, vuelve a contar y compara (PASS o FAIL por tabla), e informa el tamaño en disco de `~/docker/data/influxdb`.
4. El log completo de la corrida es la evidencia principal y se guarda en `docs/evidencia/logs/` (ver `docs/evidencia/README.md`).

## 2. Qué verifica `validacion.py`

| Verificación | Qué comprueba | Resultado posible |
| :--- | :--- | :--- |
| V1 | El servidor responde (`GET /health`) | PASS o FAIL |
| V2 | Puntos cargados por tabla igual al conteo del generador | PASS o FAIL |
| V3 | Puntos por partido igual al manifest | PASS o FAIL |
| V4 | Series por tabla igual a la estimación de cardinalidad | PASS o FAIL |
| V5 | Rango temporal (mínimo y máximo) igual al manifest | PASS o FAIL |
| V6 | Valores finales de contadores iguales al manifest, y tiros finales no menores que los goles de `partidos.csv` (Hito 5) | PASS o FAIL |
| V7 | La posesión de los dos equipos suma 100 en cada segundo del partido de referencia | PASS o FAIL |
| V8 | Idempotencia: reenviar 2.000 puntos ya cargados no cambia la cantidad | PASS o FAIL |
| V9 | Dato tardío: puntos escritos en el orden 300, 100, 200 se devuelven ordenados 100, 200, 300 | PASS o FAIL |
| V10 | Conflicto de tipos: reescribir un field flotante como entero | INFO: se registra qué respondió el servidor. Observado con InfluxDB 3 Core 3.12.0 y 3.12.1: **HTTP 400**, con el mensaje `partial write of line protocol occurred` y `invalid column type` para `posesion_pct` |
| V11 | Los minutos de mayor interacción caen poco después de un minuto de gol del Hito 5 | PASS o FAIL (se omite si el perfil dura menos de 5.400 s) |

V10 es informativa a propósito: lo que se documenta es el comportamiento **observado**, no uno supuesto.

## 3. Qué se demuestra y qué no

| Aspecto | ¿Lo demuestra este módulo? | Qué sí aporta |
| :--- | :--- | :--- |
| El modelo registra y recupera la evolución de una estadística por partido, equipo, región, servicio o jugador | **Sí** | Consultas C1 a C7 sobre datos cargados y verificados |
| Las agregaciones respetan la semántica de la medida | **Sí** | A2 muestra el error de sumar un contador acumulado frente al `MAX` correcto |
| Las series cargadas coinciden con la estimación de cardinalidad | **Sí** | V4 |
| La carga no pierde ni duplica puntos y es repetible | **Sí** | V2, V3, V5 y V8 |
| 10M+ puntos cargados en InfluxDB | **Solo si se ejecuta el perfil `completo`.** Por defecto se ejecuta `local` (1.324.800 puntos) | La estrategia y la cuenta exacta de 10.598.400 puntos están dimensionadas y verificadas por el generador |
| Rendimiento de producción | **No** | Un nodo, una máquina y un cliente Python no permiten afirmarlo |
| Latencia de consulta | **No se mide**: cada consulta se ejecuta una vez | El tiempo impreso es de orientación |
| Expiración por retención | **No** | Los datos son de 2030 y no vencen en el laboratorio; ver `retencion_y_granularidad.md` |
| Datos reales de partidos | **No** | Los datos son simulados, anclados a los CSV del Hito 5 |

## 4. Resultados de la corrida

Los resultados de esta sección se **copian del log** de la corrida; cada cifra tiene su archivo de respaldo en `docs/evidencia/logs/`. No se declara ninguna tasa ni volumen que no figure en un log.

| Dato | Valor observado | Fuente en el log |
| :--- | :--- | :--- |
| Fecha de ejecución | 2026-10-16, 20:27 (UTC-03:00) | Encabezado |
| Versión de InfluxDB | InfluxDB 3 Core 3.12.1 | Paso 1, `version del servidor` |
| Imagen | `influxdb:3-core`, id `sha256:47d815e8...3d29e38` | Paso 1, `imagen` |
| Recursos del equipo y de Docker | Intel Core i5-1335U, 12 núcleos lógicos, 7,7 GB de RAM; Docker Desktop con 12 CPUs y 3.939.123.200 bytes (≈ 3,67 GiB) de memoria | Encabezado y paso 1 |
| Perfil ejecutado | `local`: 12 partidos, 6.000 s de captura, semilla 2030, 432 series | Encabezado y paso 2 |
| Puntos cargados | 1.324.800 enviados y 1.324.800 aceptados | Paso 3, línea `TOTAL` |
| Lote y concurrencia | 5.000 líneas por lote, 4 hilos | Paso 3 |
| Tiempo de carga y puntos por segundo | 68,0 s, 19.490 puntos/s (cliente Python, 4 hilos, lote 5.000) | Paso 3, línea `TOTAL` |
| Lotes rechazados y reintentos | 0 lotes fallidos, 0 reintentos, en 267 lotes | Paso 3 |
| Validación | 23 PASS, 0 FAIL, 1 INFO (V10) | Paso 6, línea `Resumen` |
| Resumen de 1 minuto | 2.400 ventanas en `fixture2030_hist`, que cubren los 144.000 puntos originales de `estadisticas_equipo` | Paso 5, R1 |
| Medición de lotes | Ver la tabla siguiente | Paso 3b |
| Persistencia tras el reinicio | Los cinco conteos (cuatro tablas de vivo y el resumen de hist) son iguales antes y después de `docker compose restart`; tamaño en disco: 90,1 MB | Paso 7 |

### Medición de tamaño de lote y concurrencia

Se enviaron las primeras 100.000 líneas de `actividad_usuarios.lp` a `fixture2030_lab` con cada configuración (una sola ejecución por celda):

| Tamaño de lote | Hilos | Segundos | Puntos/s |
| ---: | ---: | ---: | ---: |
| 500 | 1 | 199,68 | 501 |
| 500 | 4 | 49,99 | 2.000 |
| 5.000 | 1 | 20,00 | 4.999 |
| 5.000 | 4 | 5,04 | 19.836 |
| 20.000 | 1 | 4,99 | 20.043 |
| 20.000 | 4 | 1,99 | 50.357 |

**Lectura.** Con un hilo, cada solicitud tarda alrededor de 1 segundo sin importar su tamaño: 200 lotes de 500 llevaron 199,7 s, 20 lotes de 5.000 llevaron 20,0 s y 5 lotes de 20.000 llevaron 5,0 s. Cuatro hilos dividen el tiempo aproximadamente por 4. Es **consistente con** que cada escritura espere el volcado del WAL (por defecto `wal-flush-interval` de 1 s), de modo que el tiempo depende de la cantidad de solicitudes y no de la cantidad de puntos. El log no prueba la causa; solo muestra el patrón. Consecuencia práctica: lotes grandes y varios hilos. Con lotes de 20.000 y 4 hilos el cliente superó los 50.000 puntos/s en esta máquina; la carga del perfil `local` usó el valor por defecto (5.000), que no es el más rápido de la tabla.

**Cómo leer los puntos por segundo.** El número que imprime el paso 3 es el de **un cliente Python con N hilos contra un servidor local, en esa máquina y esa corrida**. Sirve para comparar tamaños de lote entre sí y para proyectar con cautela; no es la capacidad de InfluxDB.

## 5. Limitaciones

- Las consultas se ejecutan una vez: no hay repeticiones, percentiles ni control de caché.
- La medición de lotes inserta en `fixture2030_lab` con timestamps desplazados para que cada configuración inserte puntos nuevos; la base crece con cada medición y se puede borrar.
- Los scripts Python usan solo la biblioteca estándar; el cliente HTTP es secuencial por hilo y no implementa compresión.
- El comportamiento de V10 es el de la versión de InfluxDB registrada en el log (3.12.1 en la corrida registrada en la sección 4; la primera corrida de prueba usó 3.12.0 y devolvió el mismo HTTP 400); otra versión podría diferir.
- Con el perfil `muestra` (600 s de captura) las consultas C1, C2 y C4, que miran los minutos 60 a 75, devuelven 0 filas porque esa ventana no existe en el perfil: no es un error. Con `local` y `completo` (6.000 s) sí hay datos.
