# Hito 10 — API REST integrada del Fixture 2030

**Grupo 8** · FastAPI (Python) + las seis fuentes NoSQL de los hitos anteriores

API REST que expone casos de uso del Fixture Mundial 2030 sobre **MongoDB, Neo4j,
Cassandra, Redis, InfluxDB e IRIS** mediante **adaptadores separados**. Oculta el
driver de cada motor detrás de contratos HTTP, valida las entradas, traduce los
errores y documenta todo en OpenAPI. No convierte las bases en una única
estructura ni acepta consultas arbitrarias del cliente. Un integrante ajeno al
desarrollo debe poder levantarla y probarla siguiendo estos pasos (RNF11).

## Requisitos previos
- Python 3.11 o superior.
- Docker Desktop con las bases de los hitos anteriores (se prueban las que estén levantadas).
- Puerto `8000` libre para la API.

## 1. Preparar el entorno

**Windows / PowerShell:**
```powershell
cd api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env        # ajustar si hace falta; .env no se versiona
```
**Linux / macOS / Git Bash:**
```bash
cd api
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

> **IRIS (opcional).** Su driver no está en PyPI público. Para habilitar el
> endpoint de IRIS: `pip install intersystems-irispython`. Si no se instala, ese
> endpoint responde 503 y el resto de la API funciona igual.
>
> **Cassandra (Python 3.12).** El driver `cassandra-driver` no carga en Python
> 3.12 (se removió `asyncore`, del que dependía su reactor por defecto). El
> adaptador lo detecta y cae automáticamente a `cqlsh` —el cliente oficial de
> Cassandra— ejecutado dentro del contenedor del Hito 6, sin cambiar el contrato
> de la API. Requiere que el contenedor esté levantado; su nombre se configura con
> `CASSANDRA_CONTAINER` (por defecto `fixture2030-cassandra`).

## 2. Levantar las bases a probar
No hace falta tenerlas todas (la API tolera dependencias caídas). Cada módulo del
repo tiene su `docker compose up -d`. Tanda liviana recomendada para empezar:
```
# desde la raiz del repo, en cada carpeta:
cd ../redis    && docker compose up -d
cd ../neo4j    && docker compose up -d
# MongoDB: contenedor del Hito 4 (fixture2030-mongodb)
```
InfluxDB requiere además el token del Hito 8 pegado en `.env` (`INFLUXDB3_TOKEN`).

## 3. Iniciar la API
```
scripts/iniciar_api.sh           # Linux / macOS / Git Bash
powershell -ExecutionPolicy Bypass -File .\scripts\iniciar_api.ps1   # Windows
```
- Swagger UI: http://localhost:8000/docs
- OpenAPI JSON: http://localhost:8000/openapi.json
- Estado de las fuentes: http://localhost:8000/salud

## 4. Verificar conectividad
```
scripts/verificar_conectividad.sh            # muestra que fuentes estan disponibles
```

## 5. Probar
**Tests automáticos (no requieren bases):**
```
scripts/ejecutar_pruebas.sh                  # pytest tests/ -v
```
**Colección Postman:** importar `postman/fixture2030_collection.json`, ajustar la
variable `baseUrl` si hace falta y ejecutar los casos (válidos y de error).

**Ejemplos cURL** (uno por fuente):
```bash
BASE=http://localhost:8000
curl "$BASE/equipos/ARG"                                        # MongoDB
curl "$BASE/partidos/F2030-001/eventos"                         # Neo4j
curl "$BASE/partidos/F2030-063/comentarios?instante=2030-06-22T20:23:00Z&limit=20"  # Cassandra
curl -X POST "$BASE/partidos/F2030-063/comentarios" \
     -H "Content-Type: application/json" \
     -d '{"usuarioId":"u-00042","contenido":"Gran jugada"}'     # Cassandra (escritura)
curl "$BASE/sesiones/s-demo-001"                                # Redis
curl "$BASE/partidos/F2030-018/estadisticas?desde=2030-06-13T09:00:00Z&hasta=2030-06-13T09:15:00Z"  # InfluxDB
curl "$BASE/partidos/F2030-001/detalle"                         # IRIS
```
En PowerShell, reemplazar `curl` por `Invoke-RestMethod` o usar `curl.exe`.

## 6. Detener
`Ctrl+C` detiene la API. Las bases se detienen desde cada módulo con
`docker compose stop` (no borra datos).

## Estructura
```
api/
├── app/
│   ├── routes/        # contratos HTTP por recurso (equipos, partidos, sesiones)
│   ├── services/      # casos de uso y validacion de negocio
│   ├── adapters/      # un cliente por fuente (Mongo, Neo4j, Cassandra, Redis, Influx, IRIS)
│   ├── schemas/       # validacion y modelos de request/response (Pydantic)
│   ├── core/          # config por entorno, errores, logging con request-id
│   └── main.py        # app FastAPI, OpenAPI/Swagger, manejo central de errores
├── openapi/openapi.yaml          # contrato generado desde la app
├── postman/fixture2030_collection.json
├── tests/             # pruebas de contrato y errores (sin bases)
├── scripts/           # iniciar_api, verificar_conectividad, ejecutar_pruebas (.sh y .ps1)
├── docs/              # casos de uso, arquitectura, contratos, conectividad, pruebas, evidencia
├── requirements.txt
├── .env.example       # variables de entorno (el .env real no se versiona)
└── README.md
```

## Mapa requisito → archivo
| Req. | Dónde |
| :--- | :--- |
| RF1 | `app/main.py`, `scripts/iniciar_api.*` |
| RF2 | `docs/casos_de_uso.md` |
| RF3 | `app/routes/equipos.py`, `app/adapters/mongo_adapter.py` |
| RF4 | `app/routes/partidos.py`, `app/adapters/neo4j_adapter.py` |
| RF5 | `app/adapters/cassandra_adapter.py` (lectura y escritura) |
| RF6 | `app/routes/sesiones.py`, `app/adapters/redis_adapter.py` |
| RF7 | `app/adapters/influx_adapter.py` |
| RF8 | `app/adapters/iris_adapter.py` |
| RF9 | `app/services/servicios.py` (separación de capas) |
| RF10 | `app/schemas/modelos.py`, validación en servicios |
| RF11, RF12 | `app/core/errores.py`, `app/main.py`, `docs/contratos_y_errores.md` |
| RF13 | `openapi/openapi.yaml`, Swagger UI (`/docs`) |
| RF14 | `postman/fixture2030_collection.json`, cURL en este README |
| RF15 | `tests/`, `docs/pruebas_y_evidencia.md` |
| RF16 | `app/core/config.py`, `.env.example` |
| RF17 | `/salud`, `scripts/verificar_conectividad.*` |
| RF18 | `app/core/registro.py` (request-id) |
| RF19 | `docs/contratos_y_errores.md` §5 |
| RF20 | repositorio GitHub del grupo |

## Notas de alcance
- Datos de laboratorio de los hitos previos; no se incorporan datos sensibles.
- La API no demuestra escala (millones de usuarios): se prueba en una notebook.
- IRIS y Cassandra son las fuentes más pesadas; conviene probarlas en tandas (ver `docs/conectividad_y_configuracion.md` §5).
- Los endpoints de escritura y las transiciones de estado se limitan a lo descrito; no se exponen operaciones destructivas.
