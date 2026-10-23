# Matriz de conectividad

**Grupo 8** · Fixture 2030 · Hito 11 (RF16, RNF9, RNF17, RNF18)

Esta es la matriz **interpretada**. Las matrices **generadas** por el script (una por corrida, con
todas las pruebas, su origen, su latencia y su detalle) están en
[`evidencia/corridas/<fecha>_<etiqueta>/matriz.md`](evidencia/corridas/), y la última en
[`evidencia/matriz_ultima_corrida.md`](evidencia/matriz_ultima_corrida.md).

## Significado de los estados

| Estado | Significado | Equivale en 5.6 |
| :--- | :--- | :--- |
| `disponible` | todas las pruebas positivas del producto, desde el origen de la API, terminaron OK y las rutas de la API respondieron según su contrato | `up` |
| `degradado` | el producto responde por su cliente nativo, pero el uso desde la API falla (operación incompatible o ruta fuera de contrato) | `degraded` |
| `no_disponible` | se intentó y falló una prueba de red, protocolo, identidad, contexto o lectura | `down` |
| `no_configurado` | falta configuración obligatoria para intentarlo | `not_configured` |
| `desconocido` | solo hubo pruebas SKIP (falta driver, CLI o Docker): no hay evidencia suficiente | `unknown` |
| `no_probado` | el modo elegido no incluyó pruebas de ese producto | — |

**OK** significa que *esa* prueba concreta funcionó en *ese* momento. No es una garantía de
rendimiento, escalabilidad ni disponibilidad permanente (RNF17). **SKIP** significa “no ejecutada
por falta de herramienta o configuración”, nunca “producto caído”.

## Entorno común a todas las filas

- **Fecha:** 2026-10-23 (UTC, por corrida abajo).
- **Entorno:** notebook Windows 11 (AMD Ryzen 7 5700X, 32 GB) · Docker Desktop 29.8.2 · API y
  evaluación en Python 3.11.9 (`api/.venv`) · los seis productos en contenedores (ver
  [`topologia_y_entornos.md`](topologia_y_entornos.md)).
- **Timeouts:** 3,0 s por operación en la evaluación (`TIMEOUT_S`) y 3,0 s en la API (`DEP_TIMEOUT_S`).

## Línea de tiempo de las corridas

| Hora UTC | Corrida / acción | Commit | Evidencia |
| :--- | :--- | :--- | :--- |
| 05:55 | C0: token de InfluxDB ausente → recuperado sin borrar datos | — | [`diagnostico/C0_influx_token_recuperado.txt`](evidencia/diagnostico/C0_influx_token_recuperado.txt) |
| 06:09 | Corrida exploratoria (scripts en desarrollo): detecta H1–H5 | `c2502d1+cambios_locales` | [`diagnostico/H5_influx_esquema_antes.txt`](evidencia/diagnostico/H5_influx_esquema_antes.txt) |
| 06:13 | C3: recarga de InfluxDB con los scripts actuales del Hito 8 (corrige H5) | — | [`diagnostico/C3_influx_recarga_esquema.txt`](evidencia/diagnostico/C3_influx_recarga_esquema.txt) |
| 06:18 | **Corrida `inicial`** (modo completo + API) | `c2502d1+cambios_locales` | [`corridas/20261023_031659_inicial/`](evidencia/corridas/20261023_031659_inicial/) |
| 06:19 | C1: password local de `_SYSTEM` en IRIS (corrige H3) → IRIS nativo `disponible` | — | [`diagnostico/C1_iris_password_despues.txt`](evidencia/diagnostico/C1_iris_password_despues.txt) |
| 06:19 | C2: `127.0.0.1` para InfluxDB e IRIS (corrige H4) | — | [`diagnostico/C2_ipv6_antes.txt`](evidencia/diagnostico/C2_ipv6_antes.txt), [`C2_ipv6_despues.txt`](evidencia/diagnostico/C2_ipv6_despues.txt) |
| 06:20 | Primera corrida final: aparece H7 (la capa siguiente a la credencial) | — | log en el texto de H7 |
| 06:26 | Corrida `final` original y fallas controladas (sus commits se unificaron después; reemplazadas por la re-ejecución de 19:40) | — | — |
| 19:40 | **Corrida `final`** (modo completo + API), re-ejecutada sobre el commit unificado | `82e1233` | [`corridas/20261023_164055_final/`](evidencia/corridas/20261023_164055_final/) |
| 19:41 | Re-ejecución de C1 (IRIS nativo) y C2 (TCP con `localhost` y con `127.0.0.1`) | `82e1233` | [`corridas/…_C1_iris_password/`](evidencia/corridas/20261023_164136_C1_iris_password/), [`…_C2_antes_localhost/`](evidencia/corridas/20261023_164140_C2_antes_localhost/), [`…_C2_despues_127/`](evidencia/corridas/20261023_164154_C2_despues_127/) |
| 19:41 | Fallas controladas (Redis detenido, timeout bajo, sin token) | `82e1233` | [`falla_controlada/`](evidencia/falla_controlada/) |

> La corrida `inicial` se ejecutó **después** de C3, porque la recarga del esquema de InfluxDB se
> hizo apenas se detectó H5 en la corrida exploratoria. La evidencia de H5 “antes” se conservó
> aparte. Fue un error de orden del procedimiento y queda declarado.
>
> La re-ejecución de 19:40 repite las mismas pruebas sobre el commit unificado `82e1233`. Los
> resultados y estados son idénticos a los de 06:26; solo cambian los tiempos y el `DBSIZE` de
> Redis (344 claves), porque antes de correrla se recargó la muestra del Hito 7: la sesión de
> prueba `sesion:S0001` tiene TTL de 1.800 s y había vencido.

## Matriz por dependencia

Latencia = duración de la **lectura mínima nativa desde la notebook** (driver de la API).

| Dependencia | Corrida `inicial` (06:18) | Corrida `final` (19:40) | Prueba decisiva | Latencia lectura (final) | Rutas API según contrato (final) | Diagnóstico | Evidencia |
| :--- | :--- | :--- | :--- | ---: | :---: | :--- | :--- |
| **MongoDB** | degradado | **degradado** | `find_one({_id:'ARG'})` (la del adaptador) sin resultados; `{codigo:'ARG'}` sí | 1 ms | 2/4 | H1: la API busca por `_id`; en el Hito 4 el código FIFA está en `codigo`. `/equipos/ARG` da 404 y `/jugadores` da 500 | `corridas/…_final/resultados_clientes.txt`, `…/resultados_api.txt` |
| **Neo4j** | disponible | **disponible** | handshake Bolt 5.8 + `MATCH` parametrizado | 5 ms | 3/3 | — | ídem |
| **Cassandra** | disponible | **disponible** | `OPTIONS`/`STARTUP` + lectura de una partición `LIMIT 5` | 16 ms | 3/3 | — | ídem |
| **Redis** | degradado | **degradado** | `TYPE sesion:S0001 = hash` vs. `GET` del adaptador → `WRONGTYPE` | 0 ms | 1/2 | H2: la API trata un error de tipo como “Redis no disponible” (503) | ídem |
| **InfluxDB** | degradado (TCP ~2 s por IPv6) | **degradado** | cuerpo idéntico al adaptador → `400 missing field q` | 11 ms | 1/3 | H6: el adaptador envía `query`; la API v3 exige `q`. H4 corregido (C2) | ídem + `diagnostico/C2_*` |
| **IRIS** | **no_disponible** (capa autenticación) | **degradado** | `iris.connect` OK tras C1; SQL del adaptador → `SQLCODE -1` | 2 ms | 0/2 | H3 corregido (C1). H7: alias `local` reservado en IRIS SQL | ídem + `corridas/…_C1_iris_password/` |

**Cambios de estado documentados (RF20):**

- **IRIS:** `no_disponible` (autenticación: *Password change required*) → C1 → `disponible` en
  el modo nativo (corrida `C1_iris_password`) → `degradado` en la corrida final, cuando la ruta de
  la API llegó a la capa siguiente y falló la operación (H7).
- **InfluxDB e IRIS:** TCP por nombre de ~2.040 ms → C2 → 1–15 ms (misma prueba, solo cambió la
  configuración).
- **InfluxDB (lectura nativa):** `500 Schema error: No field named pases_acum` (exploratoria) →
  C3 → `200` con 300 puntos por equipo.
- **Redis (falla controlada):** `404` (Redis arriba) → `docker stop` → `503` → `docker start` →
  `404`, sin reiniciar la API y con `DBSIZE` 344 → 344.

## `/salud` de la API frente a esta matriz

| Corrida | `/salud` (HTTP 200 siempre) | Tiempo | Lo que la matriz agrega |
| :--- | :--- | ---: | :--- |
| inicial | mongodb, neo4j, cassandra, redis = sí · influxdb, iris = no | 6.185 ms | Mongo y Redis figuran “sí”, pero sus rutas fallan (H1, H2); IRIS “no” sin decir por qué (H3) |
| final | mongodb, neo4j, cassandra, redis, **iris = sí** · influxdb = no | 2.252 ms | **IRIS figura “sí”, pero sus 2 rutas dan 503** (H7). InfluxDB “no” aunque el servicio, el token y la database están bien (H6) |

El `/salud` del Hito 10 mide si el `verificar()` de cada adaptador terminó sin excepción, no si
la operación real del caso de uso funciona. Por eso no alcanza como diagnóstico; ver
[`health_readiness.md`](health_readiness.md).
