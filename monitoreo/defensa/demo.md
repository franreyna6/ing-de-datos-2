# Demostración en vivo para la defensa (5 minutos)

**Objetivo (RF16):** mostrar en vivo que las decisiones defendidas corresponden al sistema construido. No se dice "la aplicación funciona": cada cosa que aparece en pantalla se ata a **qué base la atiende y por qué** (sección 6.3 de la consigna).

**Qué se muestra:** un partido de laboratorio completo —el inaugural del Centenario, Uruguay vs Argentina en el Estadio Centenario, 8 de junio de 2030— que atraviesa las seis bases al mismo tiempo, con hinchas virtuales generando carga real, Prometheus y Grafana midiendo, una base que se cae a propósito y una regla de negocio que IRIS rechaza en vivo.

> **Supuesto declarado:** FIFA confirmó que el Mundial arranca el 8 y 9 de junio de 2030 con tres partidos del Centenario en Montevideo, Buenos Aires y Asunción, y que la final es el 21 de julio. El rival de Uruguay es un **supuesto del grupo**. También es un supuesto el formato de 64 selecciones de la cátedra: el formato vigente es de 48 selecciones y 104 partidos, y FIFA analizó ampliarlo a 64.

## Qué agrega el Hito 13 para la demo

| Pieza | Dónde | Qué hace |
| :--- | :--- | :--- |
| Centro de control | `api/app/static/demo/index.html`, servido en **http://localhost:8000/demo** | Una pantalla, seis bases. Pestañas: partido en vivo, métricas por base (calculadas de `/metrics`, sirve de respaldo si Grafana falla), Grafana embebido, Prometheus y Swagger. HTML sin dependencias externas: funciona sin internet. |
| Rutas `/vivo/...` y `POST /sesiones` | `api/app/routes/vivo.py`, `api/app/services/vivo.py` | Escrituras que faltaban para un partido en vivo: crear, iniciar, eventos y finalizar (IRIS decide y Neo4j conecta), reloj (Redis), estadísticas (InfluxDB), sesión con TTL deslizante (Redis) y tablero con las seis bases consultadas en paralelo. |
| Reglas del partido en IRIS | `iris/src/Fixture/Vivo.cls` | La API invoca los métodos de dominio del Hito 9 (`Iniciar`, `RegistrarEvento`, `Finalizar`) por el Native API. Si una regla se viola, la API responde **409** con el motivo de IRIS. |
| Simulador del partido | `monitoreo/scripts/simular_partido_en_vivo.(ps1/sh/py)` | Árbitro + 40 hinchas virtuales: 90 minutos de juego en unos 3 minutos. Guarda la evidencia en `monitoreo/evidencia/demo_en_vivo/<etiqueta>/`. |
| Postman | `monitoreo/defensa/postman_demo_h13.json`, carpeta *Demo en vivo* | La misma secuencia, request por request, con tests (incluye el 409 esperado). |

**Integridad (RNF5):** todo lo que escribe la demo va a un partido de laboratorio `H13-DEMO-...`, marcado con `laboratorio=true` en Neo4j. La API rechaza con 400 cualquier escritura sobre otro código. El fixture real no se modifica.

## Preparación (10 minutos antes de entrar)

1. **Una sola vez** (si IRIS ya tenía las clases del Hito 9): compilar la clase nueva sin recargar datos.

   ```powershell
   "Do `$system.OBJ.Load(""/iris/src/Fixture/Vivo.cls"",""ck"")`nHalt" | docker exec -i fixture2030-iris iris session IRIS -U USER
   ```

   En bash: `printf 'Do $system.OBJ.Load("/iris/src/Fixture/Vivo.cls","ck")\nHalt\n' | docker exec -i fixture2030-iris iris session IRIS -U USER`

2. Bases, monitoreo y API, como en el Hito 13:

   ```powershell
   .\monitoreo\scripts\iniciar_monitoreo.ps1 --con-bases
   .\monitoreo\scripts\probar_iris.ps1
   .\monitoreo\scripts\iniciar_api_monitoreada.ps1        # terminal aparte
   .\monitoreo\scripts\verificar_targets.ps1 --esperar 60  # 13/13 UP
   ```

   > Si Grafana ya estaba levantado, recrearlo una vez para que tome `GF_SECURITY_ALLOW_EMBEDDING` (el iframe del centro de control): `docker compose -f monitoreo/docker-compose.yml up -d grafana`.

3. **Ensayo corto** (30 segundos): `.\monitoreo\scripts\simular_partido_en_vivo.ps1 --hinchas 10 --segundos-por-minuto 0.3 --sin-evidencia`. Tiene que terminar con "HTTP 409 (rechazado por IRIS, como debe ser)".

4. Dejar abiertas estas pestañas:
   - **http://localhost:8000/demo** (centro de control);
   - Grafana en *Last 15 minutes* (también está embebido en el centro de control);
   - una terminal en la raíz del repositorio, con los comandos de abajo ya escritos.

## Guion de la demo (5:00)

| Tiempo | Acción | Qué decir (la base, no la pantalla) |
| :--- | :--- | :--- |
| **0:00** | En la terminal: `.\monitoreo\scripts\simular_partido_en_vivo.ps1` (40 hinchas, 90' en ~3 min). Cambiar al centro de control: el partido aparece solo. | "Arranca el partido inaugural del Centenario. Cuarenta hinchas virtuales, todo pasando por la API, nunca directo a una base." |
| 0:20 | Señalar la fila de bases arriba (6 en verde) y la tarjeta **IRIS**: Programado → **EnJuego**, terna arbitral. | "IRIS creó el partido como objeto y le asignó una terna **neutral**: un árbitro uruguayo o argentino no puede dirigir este partido. La regla vive junto al dato." |
| 0:40 | Tarjeta **MongoDB** (fichas). | "La ficha completa de cada selección sale de un documento, en una lectura. El código FIFA, URU, es la clave que comparten las seis bases." |
| 1:00 | Esperar un gol. Mostrar **Neo4j** (nodo nuevo en el grafo) y el marcador. | "El gol primero lo valida IRIS: partido en juego, jugador de uno de los dos equipos. Recién después se agrega a Neo4j como nodo: gol → jugador → equipo, sin joins." |
| 1:20 | Tarjeta **Cassandra**: badge `HIT`, partición `(partido, 20:20)`. | "Después del gol, los hinchas comentan cuatro veces más. Cada comentario cae en la partición del partido y su ventana de 5 minutos. Las lecturas repetidas las absorbe Redis: casi todo es HIT." |
| 1:40 | Tarjetas **Redis** (hinchas únicos, TTL) e **InfluxDB** (posesión). | "Redis cuenta hinchas únicos con un HyperLogLog: 12 KB fijos, sean 40 o 3 millones. InfluxDB recibe un punto por segundo por equipo y lo agrega por ventanas de 10 segundos con `date_bin`." |
| **2:00** | **Falla controlada:** `docker stop fixture2030-redis` | "Ahora tiramos Redis en pleno partido." |
| 2:10 | Mostrar: tarjeta Redis en rojo (503); las otras cinco siguen; feed con badge `MISS` y leyendo de Cassandra; el simulador muestra 5xx solo en sesiones. | "Se cae **una** función: las sesiones. El partido, los goles, el feed y las estadísticas siguen. Gracias al corte rápido, la API no espera 2,4 segundos por request a una base caída." |
| 2:40 | `docker start fixture2030-redis` | "Volvió. En unos 15 segundos la API lo ve disponible y la caché se recupera sola." |
| **3:00** | Pestaña **Grafana**: requests/s, p95 contra la línea de 50 ms, aciertos de caché (la caída y la vuelta), escrituras de Cassandra por partido (`H13-DEMO-URUARG`), latencia p95 por base. | "Esto es lo que ve el equipo de operaciones: qué base está afectada, desde cuándo y qué decisión tomar. La alerta crítica tarda unos 90 segundos a propósito, para no disparar por un parpadeo." |
| **4:00** | Final del partido. El simulador intenta un gol en el minuto 95: **409**. O apretar *🚫 Probar regla de IRIS*. Mostrar el aviso rojo con el motivo. | "Partido finalizado. Intentamos cargar un gol después del final: IRIS lo rechaza con el motivo. No importa qué aplicación escriba: la regla está en la base." |
| 4:30 | Pestaña **Swagger**, sección *demo en vivo (Hito 13)*: el 409 documentado. Abajo, la **traza de requests** con la base y los ms de cada una. | "Cada request dice qué base la atendió y cuánto tardó dentro de la API. El tablero consulta las seis en paralelo: tarda lo que la más lenta, no la suma." |
| 5:00 | Fin | — |

Si se atrasa: saltear Swagger (4:30). Si la alerta no llegó, mostrar la ya registrada en `evidencia/prueba_de_falla/20261126-054628/resumen.md`.

## Flujo manual (sin simulador)

Con los botones del centro de control: **1 · Crear** → **2 · Iniciar** → **▶ Simular partido** (90' en 90 s, una sola "tribuna") o **⚽ Gol local / visitante** → **3 · Finalizar** → **🚫 Probar regla de IRIS**. La misma secuencia está en Postman, carpeta *Demo en vivo*, y en Swagger (`/docs`, sección *demo en vivo (Hito 13)*).

## Clientes nativos (si preguntan por una estructura concreta)

| Para mostrar | Comando |
| :--- | :--- |
| El partido de la demo en el grafo | En http://localhost:7474: `MATCH (ev:Evento)-[:OCURRE_EN]->(p:Partido {codigo:'H13-DEMO-URUARG'}), (ev)-[:PROTAGONIZADO_POR]->(j)-[:PERTENECE_A]->(e) RETURN ev.minuto, ev.tipo, j.nombre, e.codigo ORDER BY ev.minuto` |
| La partición de Cassandra | `docker exec -it fixture2030-cassandra cqlsh -k fixture2030_comentarios -e "SELECT ventana, count(*) FROM comentarios_por_partido WHERE partido_id='H13-DEMO-URUARG' GROUP BY ventana;"` |
| Una sesión y su TTL | `docker exec -it fixture2030-redis redis-cli --scan --pattern "sesion:s-*" --count 100` y luego `TTL sesion:<id>` / `HGETALL sesion:<id>` |
| Hinchas únicos (HyperLogLog) | `docker exec -it fixture2030-redis redis-cli PFCOUNT vivo:hinchas:H13-DEMO-URUARG` |
| El objeto en IRIS | `docker exec -it fixture2030-iris iris session IRIS -U USER` y `Write ##class(Fixture.Vivo).Estado("H13-DEMO-URUARG")` |
| La política de memoria de Redis | `docker exec -it fixture2030-redis redis-cli CONFIG GET maxmemory-policy` |

## Plan B (RNF7)

| Qué falla | Qué hacer |
| :--- | :--- |
| Una base no levanta | Es parte de la demo: en el centro de control, solo su tarjeta queda en rojo y el resto sigue. Mostrarlo así. |
| IRIS no tiene `Fixture.Vivo` compilada | Las rutas `/vivo` de escritura dan 503. Compilarla (paso 1, 10 segundos) o hacer la demo con la colección Postman del Hito 13 (lecturas). |
| Grafana no carga en el iframe | Botón *Abrir en pestaña*, o la pestaña **Las 6 bases (métricas)**, que calcula lo mismo desde `/metrics`. |
| La API no arranca | Swagger desde `api/openapi/openapi.yaml` y la evidencia: `evidencia/demo_en_vivo/<etiqueta>/resumen.md` del ensayo y las capturas de `evidencia/dashboards/`. |
| Docker o la PC no responden | Presentar desde GitHub: capturas del tablero y los informes con fecha y commit. |
| Sin proyector o sin internet | El centro de control y la presentación no necesitan internet. |
