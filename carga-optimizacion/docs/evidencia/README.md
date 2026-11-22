# Evidencia (RF16)

Todo lo que hay en esta carpeta lo generan los scripts durante corridas reales. **No se edita a mano** (RNF14).

| Ruta | Lo genera | Contenido |
| :--- | :--- | :--- |
| `<etiqueta-base>/` | `ejecutar_linea_base.py` y `validar_integridad.py` | Línea base, sin caché. |
| `<etiqueta-opt>/` | `ejecutar_prueba_optimizada.py` y `validar_integridad.py` | Repetición optimizada, con caché. |
| `comparacion.md` y `comparacion.json` | `comparar_resultados.py` | Tablas antes/después y verificación de que las condiciones son comparables. |
| `comparacion_latencias.png` | `comparar_resultados.py` (requiere matplotlib) | Percentiles por tipo de operación. |
| `comparacion_p95_en_el_tiempo.png` | `comparar_resultados.py` (requiere matplotlib) | p95 por segundo durante toda la prueba. |
| `capturas_redactadas/` | El equipo | Capturas opcionales de la terminal, sin secretos. |
| `logs_api/` | uvicorn (redirección) | Logs de la API. **No se versionan** (ver `.gitignore`). |

Dentro de cada carpeta de corrida:

| Archivo | Contenido |
| :--- | :--- |
| `metadata.json` | Trazabilidad: commit, fecha, versiones, entorno, escenario, hashes, contadores antes y después, y recursos. |
| `resumen.md` y `resumen.json` | Métricas por fase y por tipo. |
| `operaciones.csv.gz` | Una fila por operación ejecutada. |
| `serie_por_segundo.csv` | Métricas de cada segundo. |
| `recursos.csv` | Muestras de CPU y memoria. |
| `integridad.md` y `integridad.json` | Validación de integridad. |
