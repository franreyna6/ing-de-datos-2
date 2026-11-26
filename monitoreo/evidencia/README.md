# Evidencia del Hito 13

Todo lo que hay en esta carpeta lo generan los scripts de `../scripts/`. Nada se edita a mano, con una excepción documentada: en la corrida `20261126-054628` el enmascarado había tapado un valor público de laboratorio (`fixture2030`, que aparece en nombres como `fixture2030-redis`) y se restauró a mano. El código ya está corregido (`../docs/limitaciones_y_evidencia.md` §5). Cada archivo indica su fecha UTC y el commit con el que se generó (RNF2). Antes de escribir, todo pasa por el enmascarado de secretos (RNF6).

| Ruta | Qué es | Lo genera |
| :--- | :--- | :--- |
| `prometheus_targets.json` / `.md` | Última verificación de targets: estado UP/DOWN, sondas, último error, métricas expuestas por job, reglas cargadas y resultado de las consultas PromQL documentadas | `verificar_targets.py` |
| `operacion_normal/<etiqueta>/resumen.md` | Operación normal bajo carga: API, comparación entre bases (RF7) y cliente, con su `series_prometheus.csv`, `requests_cliente.csv.gz` y `metadata.json` | `ejecutar_prueba_controlada.py` (`medir_operacion_normal`) |
| `prueba_de_falla/<etiqueta>/resumen.md` | Informe de la prueba de falla controlada bajo carga (experimentos A: Redis y B: Cassandra) | `ejecutar_prueba_controlada.py` |
| `prueba_de_falla/<etiqueta>/series_prometheus.csv` | Series clave de Prometheus cada 15 s, con la fase de la prueba | ídem |
| `prueba_de_falla/<etiqueta>/serie_cliente_5s.csv` | Throughput, p50/p95 y errores vistos por el generador de carga cada 5 s | ídem |
| `prueba_de_falla/<etiqueta>/requests_cliente.csv.gz` | Una fila por request del generador | ídem |
| `prueba_de_falla/<etiqueta>/alertas.json` | Intervalos *pending* y *firing* de cada alerta (serie `ALERTS`) | ídem |
| `prueba_de_falla/<etiqueta>/alertmanager_durante_falla_*.json` | Lo que tenía Alertmanager durante cada falla | ídem |
| `prueba_de_falla/<etiqueta>/experimento_b_cassandra.json` | Respuestas de la API antes, durante y después de detener Cassandra | ídem |
| `prueba_de_falla/<etiqueta>/metadata.json` | Parámetros, horarios, commit y resumen numérico | ídem |
| `prueba_de_falla/<etiqueta>/api_redactado.log.gz` | Log de la API durante la corrida, enmascarado | `ejecutar_todo_h13.py` |
| `dashboards/prueba_<etiqueta>_*.png`, `dashboards/operacion_<etiqueta>_*.png` | Capturas del tablero con el rango exacto de cada experimento | `capturar_dashboard.py` |
| `resultados_sin_secretos/verificacion_*.json` | Historial de verificaciones de targets | `verificar_targets.py` |
| `resultados_sin_secretos/salud_<etiqueta>.json` | `/salud` de la API al empezar la corrida | `ejecutar_todo_h13.py` |
| `resultados_sin_secretos/ejecucion_<etiqueta>.log` | Toda la salida de la corrida completa | `ejecutar_todo_h13.py` |

La etiqueta `AAAAMMDD-HHMMSS` (UTC) vincula la carpeta de la prueba, sus capturas, las anotaciones del tablero y los partidos de laboratorio `H13-<etiqueta>-P1/P2` que escribió la carga.

## Corridas

| Etiqueta | Qué es |
| :--- | :--- |
| **`20261126-054628`** | **Corrida final que se defiende:** 6/6 bases, 13/13 targets, operación normal y fallas A y B |
| `20261126-040222` | Corrida 1: sin corte rápido; el "antes" de la mejora |

Las corridas intermedias, que validaron cada corrección, no se incluyen. La corrida final corrió sobre el commit `85e91ae`, anterior a compactar el historial; su código es idéntico al del commit `127501a`.

La lectura de cada una está en [`../docs/limitaciones_y_evidencia.md`](../docs/limitaciones_y_evidencia.md).
