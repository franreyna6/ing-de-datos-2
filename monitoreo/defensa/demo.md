# Demostración controlada para la defensa

Objetivo: mostrar en vivo, en unos 9 minutos (minutos 8 a 17 del [guion](guion_de_20_minutos.md)), que las decisiones defendidas corresponden al sistema construido (RF16). **Cada request se vincula con una decisión de base de datos**: nunca se dice solo "la aplicación funciona" (sección 6.3).

## Preparación (antes de entrar, unos 10 minutos)

1. Abrir Docker Desktop. Desde la raíz del repositorio:

   ```powershell
   .\monitoreo\scripts\iniciar_monitoreo.ps1 --con-bases
   ```

2. En otra terminal, levantar la API con la caché del Hito 12:

   ```powershell
   cd api; .\.venv\Scripts\Activate.ps1
   $env:CACHE_COMENTARIOS_TTL_S = "2"
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

3. Esperar a que `/salud` muestre las seis bases disponibles (Cassandra e IRIS tardan 1 a 2 minutos) y correr:

   ```powershell
   .\monitoreo\scripts\verificar_targets.ps1 --esperar 60
   ```

   Tiene que terminar sin targets DOWN.

4. Dejar abiertas estas pestañas:
   - Grafana: http://localhost:3000, tablero *Fixture 2030 - War Room*, rango *Last 15 minutes*.
   - Prometheus: http://localhost:9090/targets
   - Swagger: http://127.0.0.1:8000/docs
   - Alertmanager: http://localhost:9093
   - Postman con la colección `monitoreo/defensa/postman_demo_h13.json` importada. Sus variables ya apuntan a datos de laboratorio que devuelven 200.

5. Tener a mano, como plan B, la carpeta `monitoreo/evidencia/` y la presentación.

## Flujo 1 — Un partido atravesando las seis bases (Postman, unos 4 minutos)

Mismo partido y mismo equipo; cada request la atiende una base distinta. Lo que hay que **decir** en cada paso es la columna "Por qué esta base".

| # | Request (carpeta de Postman) | Base | Qué mostrar | Por qué esta base |
| :-- | :--- | :--- | :--- | :--- |
| 1 | `GET /salud` (Sistema) | Las 6 | Las seis fuentes en `true` | Un adaptador por base: la API no mezcla modelos |
| 2 | `GET /equipos/{codigo}` con `ARG` (MongoDB) | MongoDB | Documento con el DT como subdocumento | La ficha completa en **una** lectura, validada por JSON Schema; volumen chico y fijo (CP) |
| 3 | `GET /partidos/{codigo}/eventos` con `F2030-001` (Neo4j) | Neo4j | Goles con su jugador y su equipo | Recorrido evento → jugador → equipo sin joins: el gol es un nodo |
| 4 | `POST` y luego `GET /partidos/{codigo}/comentarios` (Cassandra) | Cassandra (+ Redis) | `ventana` en la respuesta del POST; header `X-Cache` en el GET | Escritura masiva en la partición `(partido, ventana)`; la lectura toca una sola partición; la caché del Hito 12 la protege |
| 5 | `GET /partidos/{codigo}/estadisticas` (InfluxDB) | InfluxDB | Puntos de una ventana de 5 minutos | Serie temporal: rango y agregación por tiempo; `partido_id` es tag y la posesión es field |
| 6 | `GET /partidos/{codigo}/detalle` (IRIS) | IRIS | Estado, eventos y terna del partido | Objeto con reglas: un evento solo existe en un partido `EnJuego` |
| 7 | `GET /sesiones/{id}` (Redis) | Redis | Sesión o 404 si expiró | TTL nativo. 404 (expiró) no es lo mismo que 503 (Redis caído). |
| 8 | `GET /metrics` (Monitoreo) | — | `fixture_api_requests_total` con las rutas recién usadas | Es lo que Prometheus lee cada 15 s |

Con Swagger se puede mostrar lo mismo como contrato: rutas, parámetros y códigos 400, 404 y 503 declarados.

## Flujo 2 — Observar el sistema bajo carga y ante una falla (Grafana, unos 5 minutos)

1. Generar carga mixta sobre las seis bases (dejarlo corriendo en una terminal):

   ```powershell
   api\.venv\Scripts\python.exe monitoreo\scripts\generar_carga.py --usuarios 20 --duracion 300
   ```

2. En Grafana, en unos 30 segundos, señalar:
   - throughput por ruta;
   - p50/p95/p99 contra la línea de 50 ms del SLO;
   - **latencia p95 por base**: qué base es la más lenta y por qué es razonable;
   - aciertos de caché;
   - escrituras de Cassandra por partido.

3. **Falla controlada** (no destructiva, sin borrar volúmenes):

   ```powershell
   docker stop fixture2030-redis
   ```

   Qué se ve y qué decir:
   - "Estado de salud": Redis en rojo.
   - Aciertos de caché a 0 %.
   - Las lecturas pasan a Cassandra: la serie de Cassandra sube en "Operaciones por base".
   - `/sesiones` en 503; el resto sigue en 200.
   - Mensaje: *"La caída de la caché degrada, no tira el Fixture. Lo que se pierde son las sesiones, que en el Hito 2 aceptamos perder."*
   - Al minuto aparece la alerta en Alertmanager.

4. Recuperación:

   ```powershell
   docker start fixture2030-redis
   ```

   Redis vuelve a verde y la caché recupera sus aciertos. Las anotaciones del tablero marcan los dos momentos.

Si no hay tiempo para esperar la alerta, mostrar la misma prueba ya registrada en `monitoreo/evidencia/prueba_de_falla/<etiqueta>/resumen.md` y sus capturas.

## Flujo opcional — Clientes nativos (si preguntan por una estructura concreta)

| Para mostrar | Comando |
| :--- | :--- |
| La partición de Cassandra | `docker exec -it fixture2030-cassandra cqlsh -k fixture2030_comentarios -e "SELECT partido_id, ventana, creado_en FROM comentarios_por_partido WHERE partido_id='F2030-063' AND ventana='2030-06-22 20:20:00+0000' LIMIT 5;"` |
| El TTL de una sesión | `docker exec -it fixture2030-redis redis-cli TTL sesion:S0001` y `HGETALL sesion:S0001` |
| La política de memoria de Redis | `docker exec -it fixture2030-redis redis-cli CONFIG GET maxmemory-policy` |
| Un recorrido en Neo4j | En http://localhost:7474: `MATCH (e:Evento {tipo:'Gol'})-[:PROTAGONIZADO_POR]->(j)-[:PERTENECE_A]->(t) RETURN t.codigo, count(*) AS goles ORDER BY goles DESC LIMIT 5` |
| Una serie de InfluxDB | `influxdb/scripts/consultas_temporales.py` (Hito 8) |
| Una regla de IRIS | `docker exec -it fixture2030-iris iris session IRIS` y la demo del Hito 9 (`iris/scripts/demo_terminal.txt`) |

## Plan B (RNF7): si algo falla durante la defensa

| Qué falla | Qué hacer |
| :--- | :--- |
| Una base no levanta | Es parte de la demo: mostrar en Grafana que el monitoreo la detecta, qué rutas siguen funcionando (`/salud`) y la alerta. |
| La API no arranca | Mostrar Swagger desde `api/openapi/openapi.yaml` y la evidencia del Hito 11 y de este hito (`evidencia/prometheus_targets.md`). |
| Docker Desktop o la PC no responden | Presentar desde el repositorio en GitHub: capturas de `monitoreo/evidencia/dashboards/` y el informe `evidencia/prueba_de_falla/<etiqueta>/resumen.md`, todo con fecha y commit. |
| No hay tiempo | Saltar el Flujo 2 en vivo y mostrar sus capturas (30 segundos). |
| Sin proyector o sin internet | La presentación es un HTML local (`defensa/presentacion.html`) que no necesita conexión. |

Antes de la defensa, confirmar que `git push` está hecho y que las capturas se ven en GitHub.
