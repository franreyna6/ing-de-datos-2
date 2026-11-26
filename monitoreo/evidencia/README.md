# Evidencia del Hito 13

Todo lo que hay en esta carpeta lo generan los scripts de `../scripts/`. Nada se edita a mano. Cada archivo indica su fecha UTC y el commit con el que se generó (RNF2). Antes de escribir, todo pasa por el enmascarado de secretos (RNF6).

| Ruta | Qué es | Lo genera |
| :--- | :--- | :--- |
| `prometheus_targets.json` / `.md` | Última verificación de targets: estado UP/DOWN, sondas, último error, métricas expuestas por job, reglas cargadas y resultado de las consultas PromQL documentadas | `verificar_targets.py` |
| `prueba_de_falla/<etiqueta>/resumen.md` | Informe de la prueba de falla controlada bajo carga (experimentos A: Redis y B: Cassandra) | `ejecutar_prueba_controlada.py` |
| `prueba_de_falla/<etiqueta>/series_prometheus.csv` | Series clave de Prometheus cada 15 s, con la fase de la prueba | ídem |
| `prueba_de_falla/<etiqueta>/serie_cliente_5s.csv` | Throughput, p50/p95 y errores vistos por el generador de carga cada 5 s | ídem |
| `prueba_de_falla/<etiqueta>/requests_cliente.csv.gz` | Una fila por request del generador | ídem |
| `prueba_de_falla/<etiqueta>/alertas.json` | Intervalos *pending* y *firing* de cada alerta (serie `ALERTS`) | ídem |
| `prueba_de_falla/<etiqueta>/alertmanager_durante_falla_*.json` | Lo que tenía Alertmanager durante cada falla | ídem |
| `prueba_de_falla/<etiqueta>/experimento_b_cassandra.json` | Respuestas de la API antes, durante y después de detener Cassandra | ídem |
| `prueba_de_falla/<etiqueta>/metadata.json` | Parámetros, horarios, commit y resumen numérico | ídem |
| `prueba_de_falla/<etiqueta>/api_redactado.log.gz` | Log de la API durante la corrida, enmascarado | `ejecutar_todo_h13.py` |
| `dashboards/prueba_<etiqueta>_*.png` | Capturas del tablero con el rango exacto de cada experimento | `capturar_dashboard.py` |
| `resultados_sin_secretos/verificacion_*.json` | Historial de verificaciones de targets | `verificar_targets.py` |
| `resultados_sin_secretos/salud_<etiqueta>.json` | `/salud` de la API al empezar la corrida | `ejecutar_todo_h13.py` |
| `resultados_sin_secretos/ejecucion_<etiqueta>.log` | Toda la salida de la corrida completa | `ejecutar_todo_h13.py` |

La etiqueta `AAAAMMDD-HHMMSS` (UTC) vincula la carpeta de la prueba, sus capturas, las anotaciones del tablero y los partidos de laboratorio `H13-<etiqueta>-P1/P2` que escribió la carga.
