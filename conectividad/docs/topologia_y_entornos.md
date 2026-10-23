# Topología, entornos y configuración

**Grupo 8** · Fixture 2030 · Hito 11 (RF2, RNF3, restricción “Red”)

## 1. Dónde corre cada proceso

En el entorno evaluado **la API corre en la notebook** y **cada producto corre en su propio
contenedor**, levantado con el `docker-compose.yml` de su hito. **No hay una red de Docker Compose
común**: cada compose crea su propia red y los productos no se ven entre sí. La API llega a todos
a través de los **puertos publicados** en la notebook.

```
                       NOTEBOOK (Windows 11, Docker Desktop 29.8 / WSL2)
 ┌──────────────────────────────────────────────────────────────────────────────────────┐
 │  Proceso de la API (uvicorn app.main:app, Python 3.11, api/.venv)                    │
 │  Proceso de la evaluación (conectividad/scripts, el mismo Python y los mismos drivers)│
 │        │ localhost:27017  localhost:7687  localhost:9042  localhost:6379             │
 │        │ 127.0.0.1:8181   127.0.0.1:1972                                             │
 │        ▼                                                                             │
 │  Puertos publicados por Docker Desktop (proxy de puertos en la notebook)             │
 └────────┬──────────────┬─────────────┬─────────────┬──────────────┬───────────────┬───┘
          │              │             │             │              │               │
  red fixture2030_net  neo4j_neo4j-  cassandra_   redis_default  influxdb_default iris_default
  172.19.0.0/16        network       default      172.20.0.0/16  172.18.0.0/16    172.23.0.0/16
  ┌────────────┐   ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────┐ ┌────────────┐
  │ mongodb    │   │ neo4j      │ │ cassandra  │ │ redis      │ │ influxdb     │ │ iris       │
  │ :27017     │   │ :7687 :7474│ │ :9042      │ │ :6379      │ │ :8181        │ │ :1972      │
  │ (Hito 4)   │   │ (Hito 5)   │ │ (Hito 6)   │ │ (Hito 7)   │ │ (Hito 8)     │ │ :52773     │
  └────────────┘   └────────────┘ └────────────┘ └────────────┘ └──────────────┘ └────────────┘
```

## 2. Puertos publicados frente a puertos internos

Observado con `docker port` y `docker inspect` en la notebook (2026-10-23):

| Contenedor | Red de Docker (IP interna) | Puerto interno | Publicado en la notebook | Lo usa la API |
| :--- | :--- | :--- | :--- | :---: |
| `fixture2030-mongodb` | `fixture2030_net` (172.19.0.2) | 27017 | `0.0.0.0:27017` y `[::]:27017` | sí |
| `fixture2030-neo4j` | `neo4j_neo4j-network` (172.21.0.2) | 7687 (Bolt) / 7474 (HTTP) | `0.0.0.0` y `[::]` en ambos | Bolt sí / HTTP no |
| `fixture2030-cassandra` | `cassandra_default` (172.22.0.2) | 9042 | `0.0.0.0:9042` y `[::]:9042` | sí |
| `fixture2030-redis` | `redis_default` (172.20.0.2) | 6379 | `0.0.0.0:6379` y `[::]:6379` | sí |
| `fixture2030-influxdb` | `influxdb_default` (172.18.0.2) | 8181 | **solo `127.0.0.1:8181`** | sí |
| `fixture2030-iris` | `iris_default` (172.23.0.2) | 1972 / 52773 | **solo `127.0.0.1`** en ambos | 1972 sí / 52773 no |

Los puertos internos y publicados coinciden en número, pero **no son lo mismo**: el interno solo
existe dentro de la red del contenedor, y el publicado es un listener de Docker Desktop en la
notebook. Dos consecuencias se midieron en este hito:

- **InfluxDB e IRIS publican solo en IPv4 (`127.0.0.1`).** Desde la notebook, `localhost` resuelve
  primero a `::1`. El intento IPv6 se rechaza recién después de unos 2 s, y entonces el cliente
  cae a IPv4. Cada conexión nueva de la API pagaba esos ~2 s. Como el adaptador de InfluxDB abre
  una conexión HTTP por request y el timeout de la API es de 3 s, el margen era muy chico
  (hallazgo **H4**, corrección **C2**: `127.0.0.1` en la configuración bajó la conexión TCP de
  ~2.040 ms a 1–15 ms).
- **El puerto publicado sigue aceptando TCP aunque el contenedor esté detenido.** Con
  `fixture2030-redis` detenido, la conexión TCP a `localhost:6379` tuvo **éxito** igual: el
  listener era el proxy de Docker Desktop, que cerró la conexión al recibir el `PING`. Es la
  demostración práctica de que una conexión TCP exitosa no prueba disponibilidad
  ([`evidencia/falla_controlada/`](evidencia/falla_controlada/)).

## 3. `localhost` no significa lo mismo en todos lados (RNF3)

`prueba_tcp.py --desde-contenedor` repite las pruebas **desde dentro** del contenedor de Redis
(`bash /dev/tcp`, sin instalar nada). Resultado de la corrida final:

| Desde | Destino | Resultado | Lectura |
| :--- | :--- | :--- | :--- |
| notebook | `localhost:27017` | éxito | puerto publicado de Mongo |
| notebook | `mongodb:27017` | **host no resuelto** | el nombre del servicio solo existe dentro de la red de Compose del Hito 4 |
| contenedor Redis | `localhost:6379` | éxito | `localhost` es el propio contenedor de Redis |
| contenedor Redis | `localhost:27017` | **falla** | Mongo no corre en ese contenedor: `localhost` NO es la notebook |
| contenedor Redis | `host.docker.internal:27017` | éxito | así se alcanza un puerto publicado desde un contenedor (Docker Desktop) |
| contenedor Redis | `fixture2030-mongodb:27017` | **host no resuelto** | otro contenedor en otra red de Compose |

Por eso los clientes nativos que corren con `docker exec` (mongosh, cqlsh, …) se marcan con
**origen = contenedor**: prueban el producto, no la ruta que usa la API.

## 4. Si la API corriera en un contenedor

No es el entorno evaluado, pero queda documentado qué cambiaría:

| Aspecto | API en la notebook (evaluado) | API en un contenedor |
| :--- | :--- | :--- |
| Host de cada producto | `localhost` / `127.0.0.1` | nombre de servicio (`mongodb`, `neo4j`, …) |
| Puerto | publicado | interno (el mismo número en este repo) |
| Red | no hace falta | la API debe unirse a **cada** red (`fixture2030_net`, `neo4j_neo4j-network`, …) o a una red común externa |
| Alternativa sin redes | — | `host.docker.internal:<puerto publicado>` (solo Docker Desktop) |
| Fallback a `cqlsh` de Cassandra | `docker exec` desde la notebook | requiere el socket de Docker dentro del contenedor (no recomendado) |
| IPv6 / `localhost` (H4) | aplica | no aplica (DNS interno de Docker, IPv4) |

## 5. Configuración

- **Fuente:** variables de entorno con los mismos nombres que la API. La evaluación las toma, en
  orden de prioridad, del **entorno**, de `config/configuracion.env` (excluido de Git) y de
  valores por defecto **sin secretos** ([`scripts/lib_conectividad.py`](../scripts/lib_conectividad.py)).
- **Plantilla:** [`config/configuracion-ejemplo.env`](../config/configuracion-ejemplo.env), con
  `<...>` donde va una credencial.
- **Token de InfluxDB:** no se copia. `INFLUXDB3_TOKEN_FILE=../influxdb/.influxdb3-token` apunta al
  archivo que crea el Hito 8. Cuando la evaluación levanta la API (`--iniciar-api`), le pasa el
  valor por variable de entorno al proceso hijo, nunca por línea de comandos ni por archivo.
- **Salida:** la capa de configuración muestra cada variable con su origen (`entorno`,
  `configuracion.env`, `defecto`, `archivo INFLUXDB3_TOKEN_FILE`). Las passwords y el token se
  describen (“definido, 11 caracteres, oculto”) y las URI se enmascaran (`mongodb://admin:****@…`).

| Variable | Valor de ejemplo | Diferencia de entorno |
| :--- | :--- | :--- |
| `MONGODB_URI` | `mongodb://<usuario>:<password>@localhost:27017/?authSource=admin` | en contenedor: `@mongodb:27017` |
| `NEO4J_URI` | `bolt://localhost:7687` | en contenedor: `bolt://neo4j:7687` |
| `CASSANDRA_HOST` | `localhost` | en contenedor: `cassandra` |
| `REDIS_URL` | `redis://localhost:6379/0` | en contenedor: `redis://redis:6379/0` |
| `INFLUX_URL` | `http://127.0.0.1:8181` | en contenedor: `http://influxdb:8181` |
| `IRIS_HOST` | `127.0.0.1` | en contenedor: `iris` |
| `TIMEOUT_S` | `3.0` | límite de cada operación de la evaluación (RNF5) |
| `DEP_TIMEOUT_S` | `3.0` (de la API) | se altera solo en el escenario `timeout_bajo`, en una instancia separada |

> **Nota sobre `api/.env.example`.** La plantilla de la API sigue con `localhost` para InfluxDB e
> IRIS. No se modificó porque el alcance acordado para este hito fue **no tocar la API**; la
> recomendación queda en [`diagnostico_de_fallas.md`](diagnostico_de_fallas.md) (H4).
