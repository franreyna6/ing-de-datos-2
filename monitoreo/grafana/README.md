# Grafana — tablero "Fixture 2030 - War Room"

Grafana no guarda datos: consulta a Prometheus y los muestra (Clase 14). Todo lo de esta carpeta se **provisiona** al arrancar el contenedor, así que el tablero es el mismo en cualquier máquina y está versionado en Git.

| Archivo | Qué hace |
| :--- | :--- |
| `provisioning/datasources/prometheus.yml` | Crea el datasource `Prometheus Fixture 2030` (uid `prometheus-fixture2030`) apuntando a `http://prometheus:9090`. |
| `provisioning/dashboards/fixture2030.yml` | Carga los tableros de `dashboards/` en la carpeta *Fixture 2030*. Desde la interfaz no se pueden pisar (`allowUiUpdates: false`): el tablero oficial es el del repositorio. |
| `dashboards/fixture2030-war-room.json` | El tablero (uid `fixture2030-war-room`). Es la página de inicio de Grafana. |

**Acceso:** http://localhost:3000. Sin login se ve en modo solo lectura (rol Viewer anónimo, solo en `127.0.0.1`). El usuario administrador y su contraseña están en `monitoreo/.env`, que no se sube a Git y lo crea `scripts/iniciar_monitoreo` con una contraseña al azar.

## Cómo leer el tablero

Cada panel tiene título, unidad, leyenda y una descripción (ícono **i**) con la consulta PromQL y la ventana usada (RNF4). El rango por defecto son los últimos 15 minutos, con refresco cada 10 s.

| Fila | Panel | Pregunta que responde | Umbral dibujado |
| :--- | :--- | :--- | :--- |
| Estado de salud | Vista de infraestructura | ¿Cada base responde a su exporter, su endpoint nativo o la sonda externa? | Verde = OK, rojo = CAÍDA |
| Estado de salud | Vista de la API | ¿La API puede usar cada base? Es un chequeo de protocolo: ping, consulta mínima. | Verde = OK, rojo = CAÍDA |
| Resumen | 6 indicadores | Requests/s, p95 de la API, % de 5xx, aciertos de caché, escrituras en Cassandra y alertas activas | p95 > 50 ms; 5xx > 1 %; caché < 80 % |
| API | Throughput por ruta | ¿Cuánto tráfico recibe cada ruta? | — |
| API | Latencia p50/p95/p99 | ¿El tiempo de respuesta cumple el SLO? | Línea roja en 50 ms (SLO) |
| API | Respuestas no exitosas | ¿Hay fallas (5xx) o pedidos inválidos o inexistentes (4xx)? | — |
| Comparación entre bases | Latencia p95 por base | ¿Qué base es la más lenta? Separa un problema de la API de uno de la base. | — |
| Comparación entre bases | Operaciones por base | ¿Cuánto trabajo recibe cada base y cuántas llamadas fallan? | — |
| Caché y Cassandra | Tasa de aciertos | ¿La caché del Hito 12 está funcionando? | Línea roja en 80 % |
| Caché y Cassandra | Memoria de Redis | ¿Redis se acerca a su `maxmemory` de 100 MB? | Línea roja en 85 % (Clase 14) |
| Caché y Cassandra | Escrituras por partido | ¿Qué partido concentra las escrituras? | — |
| Métricas propias | MongoDB opcounters, IRIS globals, sondas | Métricas de cada motor y tiempo de conexión desde afuera | — |
| Métricas propias | Chequeo de disponibilidad, duración del scrape, muestras por scrape | Salud del propio monitoreo y cardinalidad | — |
| Corte rápido | Llamadas evitadas por base y estado del corte | ¿La API dejó de intentar una base caída? Es la mejora del Hito 13. | ABIERTO en rojo |
| Corte rápido | InfluxDB: requests HTTP | Métrica propia del endpoint nativo de InfluxDB 3 | — |

**Variables:** `Base (fuente)` filtra la comparación entre bases y `Partido` filtra las escrituras de Cassandra.

**Anotaciones:**
- *Eventos de la prueba controlada:* las marcas de inicio de carga, `docker stop` y `docker start` que escribe `scripts/ejecutar_prueba_controlada.py`.
- *Alertas de Prometheus (firing):* los tramos en que cada alerta estuvo disparada. No incluye `SondaExternaFallida` ni `TargetDeMonitoreoCaido`: son alertas sobre el propio monitoreo, siguen en Alertmanager y, si se dibujaran, taparían los gráficos.

Las dos aparecen sobre todos los gráficos de serie temporal.

## Capturas reproducibles

Las capturas de `../evidencia/dashboards/` no son capturas de pantalla manuales. Las genera `scripts/capturar_dashboard.py` con el servicio `grafana-image-renderer`, usando el rango de tiempo **exacto** de cada prueba. Mientras Prometheus conserve los datos (7 días), se pueden volver a generar:

```powershell
.\monitoreo\scripts\ejecutar_prueba_controlada.ps1   # las genera al terminar
api\.venv\Scripts\python.exe monitoreo\scripts\capturar_dashboard.py --ultimos-minutos 15
```
