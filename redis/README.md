# Hito 7 — Caché de usuarios y sesiones del Fixture 2030 (Redis)

**Grupo 8** · Redis (`latest`) + Docker Compose

Módulo de estado transitorio y lectura rápida: **sesiones de usuarios** con expiración por
inactividad, **caché** de las fichas de partido y de equipo con invalidación cuando cambia la
fuente de verdad, y **operaciones concurrentes** (visitas y votos) sin pérdida de actualizaciones.
Redis **no reemplaza** a MongoDB, Neo4j ni Cassandra: guarda copias y estado temporal. Un
integrante ajeno al desarrollo debe poder levantarlo y repetir las pruebas siguiendo estos pasos (RNF3).

> **Ambiente de un solo nodo (standalone).** Este laboratorio **no** es una topología de alta
> disponibilidad: no tiene réplicas, Sentinel ni Redis Cluster. Las diferencias y los pasos para
> llegar a esas topologías están en [`docs/memoria_y_escalabilidad.md`](docs/memoria_y_escalabilidad.md).

## Requisitos previos
- Docker Desktop con `docker compose`.
- Puerto `6379` libre.
- Python 3 (solo para regenerar la muestra; usa solo la biblioteca estándar).

## 1. Puesta en marcha (RF1)
```
docker compose up -d
docker compose ps
docker compose logs -f redis
```
El primer inicio descarga `redis:latest`. Los datos persisten en `~/docker/data/redis` (RNF2).

> Si Compose no expande `~` en tu sistema, reemplazar esa ruta en `docker-compose.yml` por la ruta
> absoluta de tu carpeta personal.

**Verificar el servidor** con las herramientas que trae el contenedor:
```
docker exec -it fixture2030-redis redis-cli      # cliente interactivo
PING                                             # debe responder PONG
INFO server                                      # versión observada de redis:latest
INFO persistence
```

### Nota sobre `redis:latest` (RNF1, RNF10)
La etiqueta `latest` puede cambiar de una fecha a otra, por eso **cada corrida registra la versión
observada** (`docs/evidencia/logs/00_ambiente.log` y `01_inicializacion.log`). Para actualizar la
imagen antes de una nueva prueba: `docker compose pull redis` y `docker compose up -d`.

## 2. Ejecutar los scripts

### 2.1 Todo junto, guardando la evidencia (recomendado)
```
bash scripts/ejecutar_todo.sh                                              # Linux / macOS / Git Bash
powershell -ExecutionPolicy Bypass -File .\scripts\ejecutar_todo.ps1       # Windows
```
Tarda unos minutos (la medición y la presión de memoria son los pasos más largos) y deja un log por paso en `docs/evidencia/logs/`. Para omitir la
prueba de presión de memoria: `SIN_PRESION=1 bash scripts/ejecutar_todo.sh` (PowerShell:
`$env:SIN_PRESION = 1` antes de ejecutar).

### 2.2 Un script a la vez
Los scripts `.redis` se ejecutan **dentro del contenedor** con el ejecutor de bloques:
```
docker exec fixture2030-redis sh /scripts/ejecutar_bloques.sh /scripts/sesiones.redis
```
> **Por qué un ejecutor y no `redis-cli < archivo`:** `redis-cli` no admite comentarios (`#`) al leer
> comandos desde un archivo (responde `ERR unknown command '#'`). El ejecutor muestra los
> comentarios, envía cada comando y muestra su respuesta, de modo que la salida sirve como
> evidencia. Entiende dos directivas dentro de comentarios: `#@esperar N` (pausa) y
> `#@campos a|b` (filtra la salida de `INFO`).
>
> En Git Bash (Windows), si una ruta `/scripts/...` falla por conversión de rutas, anteponer
> `MSYS_NO_PATHCONV=1`.

Orden recomendado (cada uno es idempotente; repetirlos no duplica datos):

| # | Script | Para qué sirve (RNF9) |
| :--- | :--- | :--- |
| 1 | `inicializacion.redis` | Verifica el servidor; registra versión, persistencia y política de memoria |
| 2 | `carga_muestra.redis` (modo `carga`) | Carga la muestra: 200 sesiones, copias de caché, visitas y votos |
| 3 | `sesiones.redis` | Ciclo de vida de la sesión: crear, renovar, suspender, vencer, cerrar |
| 4 | `cache.redis` | Cache-Aside: miss, carga con TTL, hit, invalidación, trampa del `SET` sin `EX` |
| 5 | `concurrencia.redis` | Comandos atómicos: contador, votos y ranking Top N, renovación con `MULTI/EXEC` |
| 6 | `concurrencia_paralela.sh` | 4 clientes en paralelo: atómicos contra el antipatrón `GET`+`SET` |
| 7 | `auditoria_ttl.sh` | Verifica con `SCAN` que todo dato temporal tiene TTL |
| 8 | `metricas.redis` | `INFO`: hits, misses, expiradas, evictadas, memoria |
| 9 | `medicion.sh` | Tiempo por comando y tasa de hit del Cache-Aside |
| 10 | `presion_memoria.sh` | TTL contra evicción y `noeviction` (restaura todo al terminar) |
| — | `persistencia.redis` | Estado que debe sobrevivir al reinicio (lo usa `ejecutar_todo`) |
| — | `limpieza.sh` | **Opcional.** Borra claves por prefijo con `SCAN` + `DEL` |

El modo `carga` se invoca así:
```
docker exec fixture2030-redis sh /scripts/ejecutar_bloques.sh /scripts/carga_muestra.redis carga
```

### 2.3 Regenerar la muestra (opcional)
```
python scripts/generar_datos.py
```
Con semilla fija (2030) produce siempre el mismo `scripts/carga_muestra.redis`.

## 3. Detener, reiniciar y empezar de cero
```
docker compose stop           # detiene sin borrar datos
docker compose start          # vuelve a levantarlo con los mismos datos
docker compose restart redis  # reinicio; los datos y los TTL se conservan (ver 12_persistencia.log)
docker compose down           # elimina el contenedor, NO el directorio de datos
```
Para empezar completamente de cero hay que ejecutar `docker compose down` y borrar a mano
`~/docker/data/redis`, **únicamente con esa intención explícita**. Para vaciar solo las claves del
módulo: `docker exec fixture2030-redis sh /scripts/limpieza.sh todo`.

## 4. Evidencia (RF13)
Cada corrida de `ejecutar_todo.*` deja en `docs/evidencia/logs/` un log por paso (ambiente, versión,
TTL observados, métricas consultadas y resultados de las pruebas). Detalle y registro del
ambiente en [`docs/evidencia/README.md`](docs/evidencia/README.md).

## Estructura del proyecto
```
redis/
├── docker-compose.yml               # Redis latest + AOF/RDB + maxmemory + persistencia + scripts montados
├── scripts/
│   ├── inicializacion.redis         # verificación del servidor y del ambiente (RF1, RF10)
│   ├── carga_muestra.redis          # muestra generada: sesiones, caché, visitas, votos (RF11)
│   ├── sesiones.redis               # ciclo de vida de la sesión (RF3-RF5)
│   ├── cache.redis                  # Cache-Aside e invalidación (RF6, RF7)
│   ├── concurrencia.redis           # operaciones atómicas y ranking (RF8, RF9)
│   ├── metricas.redis               # métricas del servidor (RF12, RF13)
│   ├── persistencia.redis           # estado que debe sobrevivir al reinicio (RNF2)
│   ├── ejecutar_bloques.sh          # ejecutor de los .redis (comentarios, pausas, MULTI/EXEC)
│   ├── concurrencia_paralela.sh     # prueba con 4 clientes simultáneos (RF8)
│   ├── auditoria_ttl.sh             # verifica TTL en datos temporales (RNF6)
│   ├── medicion.sh                  # tiempo por comando y tasa de hit (RF12)
│   ├── presion_memoria.sh           # evicción contra TTL (RF10)
│   ├── limpieza.sh                  # limpieza opcional por prefijo
│   ├── lib_redis.sh                 # funciones comunes (SCAN, INFO, tiempo)
│   ├── generar_datos.py             # generador reproducible de la muestra (RF11)
│   └── ejecutar_todo.sh / .ps1      # corrida completa con logs (RF13)
├── data/origen/                     # CSV del Hito 5: partidos, equipos, participaciones, jugadores
├── docs/
│   ├── patrones_de_acceso.md        # problema de concurrencia + patrones de acceso (RF2)
│   ├── modelo_clave_valor.md        # claves, estructuras, atributos, nomenclatura (RNF4, RNF5)
│   ├── ciclo_de_vida_e_invalidacion.md   # sesiones, caché, invalidación, clave ausente (RF4-RF7)
│   ├── concurrencia.md              # atomicidad y prueba en paralelo (RF8, RF9)
│   ├── memoria_y_escalabilidad.md   # TTL contra evicción, política, límites, escala (RF10)
│   ├── datos_cargados.md            # origen, cantidad y distribución (RF11)
│   ├── rendimiento.md               # métodos, resultados, métricas y límites (RF12)
│   ├── coherencia_con_el_tpo.md     # relación con los hitos anteriores y los requisitos
│   └── evidencia/                   # logs de ejecución + distribución generada
└── README.md
```

## Mapa requisito → archivo
| Req. | Dónde |
| :--- | :--- |
| RF1 | `docker-compose.yml`, este README (§1), `scripts/inicializacion.redis` |
| RF2 | `docs/patrones_de_acceso.md` |
| RF3, RF5 | `scripts/sesiones.redis`, `docs/modelo_clave_valor.md` §2.1 |
| RF4 | `scripts/sesiones.redis`, `docs/ciclo_de_vida_e_invalidacion.md` §1 |
| RF6, RF7 | `scripts/cache.redis`, `docs/ciclo_de_vida_e_invalidacion.md` §2-§3 |
| RF8 | `scripts/concurrencia.redis`, `scripts/concurrencia_paralela.sh`, `docs/concurrencia.md` |
| RF9 | `scripts/concurrencia.redis` (bloques 2 y 3), `docs/concurrencia.md` §2 |
| RF10 | `docker-compose.yml`, `scripts/presion_memoria.sh`, `docs/memoria_y_escalabilidad.md` |
| RF11 | `scripts/carga_muestra.redis`, `scripts/generar_datos.py`, `docs/datos_cargados.md` |
| RF12 | `scripts/medicion.sh`, `scripts/metricas.redis`, `docs/rendimiento.md` |
| RF13 | `docs/evidencia/` |
| RNF1 | `docker-compose.yml` (`redis:latest`) |
| RNF2 | `docker-compose.yml` (`~/docker/data/redis`), `docs/evidencia/logs/12_persistencia.log` |
| RNF3 | este README |
| RNF4 | `docs/modelo_clave_valor.md` §2 |
| RNF5 | `docs/modelo_clave_valor.md` §1 |
| RNF6 | `docs/ciclo_de_vida_e_invalidacion.md` §5, `scripts/auditoria_ttl.sh` |
| RNF7 | muestra sintética sin datos personales ni tokens (`docs/datos_cargados.md` §1) |
| RNF8 | `SCAN` en `sesiones.redis`, `lib_redis.sh`; nunca `KEYS *` |
| RNF9 | comentarios y bloques de cada script; scripts separados por inicio, carga, sesiones, caché, concurrencia, métricas y limpieza |
| RNF10 | `docs/evidencia/logs/00_ambiente.log`, `09_medicion.log`, `docs/rendimiento.md` §1 |

## Mapa apartado del análisis → archivo
| Apartado | Dónde |
| :--- | :--- |
| Problema de concurrencia | `docs/patrones_de_acceso.md` §1 |
| Patrones de acceso | `docs/patrones_de_acceso.md` §2 |
| Modelo clave/valor | `docs/modelo_clave_valor.md` |
| Ciclo de vida | `docs/ciclo_de_vida_e_invalidacion.md` §1, §5, §6 |
| Fuente de verdad y caché | `docs/ciclo_de_vida_e_invalidacion.md` §2-§4 |
| Concurrencia | `docs/concurrencia.md` |
| Memoria y escalabilidad | `docs/memoria_y_escalabilidad.md` |
| Datos cargados | `docs/datos_cargados.md` |
| Operaciones Redis | este README (§2.2) |
| Pruebas y evidencia | `docs/rendimiento.md`, `docs/evidencia/` |
| Coherencia con el TPO | `docs/coherencia_con_el_tpo.md` |
