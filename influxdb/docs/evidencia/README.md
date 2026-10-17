# Evidencia del Hito 8

Esta carpeta guarda lo que respalda cada afirmación de `docs/pruebas_y_evidencia.md`.

## Contenido

| Archivo | Qué es | Cómo se genera |
| :--- | :--- | :--- |
| `logs/ejecucion_local_20261016_202726.log` | Log completo de la corrida del perfil `local` (1.324.800 puntos): fecha, versión de InfluxDB, imagen, recursos, generación, carga, medición de lotes, consultas C1 a C7, agregaciones A1 a A7 y R1, validación V1 a V11 y prueba de persistencia | `ejecutar_todo.ps1 -Perfil local -MedirLotes -ProbarPersistencia` |

## Cómo se lee el log

| Sección del log | Qué demuestra | Requisito |
| :--- | :--- | :--- |
| 1. Inicialización | Versión del servidor, imagen, recursos y bases creadas | RF1, RNF10 |
| 2. Generación | Puntos y series por tabla | RF7, RF12 |
| 3. Carga por lotes | Puntos enviados y aceptados, lotes fallidos, reintentos, puntos por segundo | RF13 |
| 3b. Medición | Tamaño de lote y concurrencia | RF13 |
| 4. Consultas temporales | C1 a C7 | RF8 |
| 5. Agregaciones | A1 a A7 y resumen de 1 minuto (R1) | RF9 |
| 6. Validación | V1 a V11 | RF14 |
| 7. Persistencia | Conteos antes y después de reiniciar el contenedor | RNF2 |

## Para reproducirla

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\ejecutar_todo.ps1 -Perfil local -MedirLotes -ProbarPersistencia
```

Cada ejecución crea un log nuevo con fecha en `logs/`. El log no contiene el token (RNF7).
