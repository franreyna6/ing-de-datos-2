# Hito 12 — Pruebas de carga y optimización (Fixture 2030, Grupo 8)

Prueba de carga reproducible sobre un flujo real de la API del Hito 10: el **pico de comentarios después de un gol**. Muchos usuarios leen y publican comentarios del mismo partido al mismo tiempo, a través de `GET /partidos/{codigo}/comentarios` y `POST /partidos/{codigo}/comentarios`, que se resuelven en Cassandra (Hito 6).

El trabajo sigue el ciclo de la Clase 13:

1. Medir una línea base.
2. Formular una hipótesis.
3. Cambiar una sola cosa: caché de lectura en Redis con TTL corto.
4. Repetir el mismo escenario.
5. Comparar resultados y verificar la integridad.

Además se diseña una vista analítica (Data Mart) y se compara el flujo con una alternativa relacional.

> **Resultado.** Con la caché de 2 s, el p95 de las lecturas bajó de 24,23 a 7,05 ms y las lecturas que llegaron a Cassandra bajaron de 24.469 a 456. No hubo errores ni pérdida de datos. El detalle está en `docs/hipotesis_y_optimizacion.md`, sección 5.

> **Estado de la evidencia.** Los scripts generan todos los resultados en `docs/evidencia/<corrida>/`. Ningún número de este repositorio fue escrito a mano: todo valor medido sale de una corrida real y queda asociado a su fecha, commit, configuración y entorno (RNF2, RNF14).

## Mapa de la carpeta

| Ruta | Contenido |
| :--- | :--- |
| `instrucciones-del-entorno.md` | Qué servicios levantar, versiones a registrar y límites de la notebook. |
| `config/escenario.json` | El escenario de carga: fases, usuarios, mezcla, distribución y corte seguro. |
| `config/configuracion-ejemplo.env` | URL de la API y nombres de contenedores. No tiene secretos. |
| `datos/README.md` | Cómo se generan los datos de prueba y su relación con el volumen proyectado. |
| `scripts/preparar_datos.py` | **Preparación**: genera el plan de operaciones con una semilla fija. |
| `scripts/ejecutar_linea_base.py` | **Carga y medición** con la API sin caché. |
| `scripts/ejecutar_prueba_optimizada.py` | **Carga y medición** con la API con caché, mismo escenario. |
| `scripts/ejecutar_carga.py` | Generador de carga común a las dos corridas. |
| `scripts/validar_integridad.py` | **Validación**: compara lo enviado con lo que quedó en Cassandra y Redis. |
| `scripts/comparar_resultados.py` | **Comparación** antes/después, con tablas y gráficos. |
| `scripts/limpiar_datos_de_prueba.py` | **Limpieza opcional**: borra solo lo que escribió una corrida. |
| `docs/flujo_y_escenario_de_carga.md` | Flujo elegido, escenario y criterios de éxito (RF1, RF2). |
| `docs/linea_base.md` | Qué se registra en la línea base y dónde está (RF4, RF5, RF6). |
| `docs/hipotesis_y_optimizacion.md` | Hipótesis, cambio aplicado, costo y decisión (RF7 a RF11). |
| `docs/integridad_y_limitaciones.md` | Controles de integridad, hallazgos y límites (RF15, RNF6, RNF14). |
| `docs/integracion_data_mart.md` | Pregunta analítica, fuentes, grano, ETL y procedencia (RF12, RF13). |
| `docs/comparacion_relacional.md` | Alternativa relacional del mismo flujo (RF14). |
| `docs/evidencia/` | Resultados de cada corrida, la comparación y los gráficos (RF16). |

El cambio de código está en la API, encapsulado detrás de una variable:

- `api/app/services/servicios.py`, `api/app/adapters/redis_adapter.py`, `api/app/routes/partidos.py`, `api/app/core/config.py`: caché opcional de lectura, controlada por `CACHE_COMENTARIOS_TTL_S`. Con `0` (el valor por defecto) la API se comporta igual que en el Hito 10.
- `api/app/main.py`: header `X-Duracion-ms`, con el tiempo medido dentro de la API.

## Requisitos

- Docker Desktop con los contenedores de Cassandra (Hito 6) y Redis (Hito 7).
- El entorno de Python de la API del Hito 10 (`api/.venv`). Los scripts usan solo la biblioteca estándar.
- **Opcional pero recomendado**: `pip install psutil matplotlib` dentro del mismo `api/.venv`. `psutil` mide la CPU y memoria de la API y de la máquina; `matplotlib` genera los gráficos.
- Alrededor de 1 GB libre de RAM además de los contenedores. Cada corrida dura unos 4 minutos.

## Orden de ejecución

Hacen falta **dos terminales**. La terminal **A** corre la API y la **B** corre los scripts. Los comandos son para PowerShell, desde la raíz del repo; en bash cambian solo la activación del entorno y la forma de definir variables (ver `instrucciones-del-entorno.md`).

**0. Antes de medir.** Commitear el código, porque cada corrida registra el commit (RNF2). Después levantar Cassandra y Redis si no estaban:

```powershell
cd cassandra; docker compose up -d; cd ..
cd redis;     docker compose up -d; cd ..
```

**1. Preparar los datos (terminal B).** Se hace una sola vez y el resultado es determinístico:

```powershell
api\.venv\Scripts\Activate.ps1
python carga-optimizacion\scripts\preparar_datos.py
```

**2. Línea base.**

En la terminal A, levantar la API sin caché y sin `--reload`. El log va a un archivo para que la consola no frene la API:

```powershell
cd api; .\.venv\Scripts\Activate.ps1
$env:CACHE_COMENTARIOS_TTL_S="0"
python -m uvicorn app.main:app --port 8000 *> ..\carga-optimizacion\docs\evidencia\logs_api\api_linea_base.log
```

En la terminal B, correr la carga y la validación:

```powershell
python carga-optimizacion\scripts\ejecutar_linea_base.py
python carga-optimizacion\scripts\validar_integridad.py <etiqueta-base>
```

**3. Prueba optimizada.**

En la terminal A, cortar la API con Ctrl+C y reiniciarla con la caché prendida:

```powershell
$env:CACHE_COMENTARIOS_TTL_S="2"
python -m uvicorn app.main:app --port 8000 *> ..\carga-optimizacion\docs\evidencia\logs_api\api_optimizada.log
```

En la terminal B:

```powershell
python carga-optimizacion\scripts\ejecutar_prueba_optimizada.py
python carga-optimizacion\scripts\validar_integridad.py <etiqueta-opt>
```

**4. Comparar (terminal B).**

```powershell
python carga-optimizacion\scripts\comparar_resultados.py <etiqueta-base> <etiqueta-opt>
```

**5. Confirmar el cliente de Cassandra que usó la API.** Tiene que ser el mismo en las dos corridas:

```powershell
Select-String -Path carga-optimizacion\docs\evidencia\logs_api\*.log -Pattern "modo=" | Select-Object -First 2
```

Cada script de carga imprime la `<etiqueta>` de la corrida y deja todo en `docs/evidencia/<etiqueta>/`. Antes de empezar verifica que la API esté en el modo correcto y se niega a correr si no lo está: la línea base exige `X-Cache: OFF`, y la optimizada exige `MISS` y luego `HIT`.

Si la notebook no da abasto (el corte seguro detiene la prueba), repetir **ambas** corridas con el mismo `--escala 0.5`.

Los logs de la API no se versionan, porque son grandes y se regeneran (ver `.gitignore`).

### Limpieza segura (opcional)

```powershell
python carga-optimizacion\scripts\limpiar_datos_de_prueba.py <etiqueta>              # muestra qué borraría
python carga-optimizacion\scripts\limpiar_datos_de_prueba.py <etiqueta> --confirmar  # borra
```

La limpieza borra solo los partidos de laboratorio de esa corrida (`H12-<etiqueta>-P*`) y sus claves de caché. No toca volúmenes, sesiones, otros datos ni la evidencia. Hay que correrla **después** de validar la integridad, porque la validación lee esas particiones. No es necesaria para repetir la prueba, porque cada corrida escribe en partidos propios.

## Correcciones de hitos anteriores aplicadas acá

| Corrección | Cómo se aplica en este hito |
| :--- | :--- |
| Hito 5: la evidencia debe coincidir exactamente con la operación declarada. | Cada corrida guarda cada operación ejecutada (`operaciones.csv.gz`), con su método, código HTTP, latencia y estado de caché. Lo que dicen las tablas sale de ahí. |
| Hito 7: `volatile-lru` puede expulsar sesiones vigentes. | La caché agrega claves con TTL a la misma instancia que las sesiones, así que el riesgo existe. Se mide `evicted_keys` y la cantidad de sesiones antes y después, y el riesgo se discute en `hipotesis_y_optimizacion.md`. |
| Hito 8: diferenciar lo medido de lo proyectado. | La sección *Escalabilidad* de `integridad_y_limitaciones.md` separa el volumen probado del proyectado, y ningún valor proyectado aparece como medido. |
| Hito 10: evidencia de que cada endpoint consulta su base real. | El contador de lecturas de Cassandra (`nodetool`) y el header `X-Cache` muestran cuándo una lectura fue a Cassandra y cuándo la resolvió Redis. |
