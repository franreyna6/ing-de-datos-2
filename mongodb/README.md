# Hito 4 — Módulo Documental de Equipos y Jugadores (Fixture 2030)

**Grupo N.º 8** · Clase 4 · MongoDB 7 sobre Docker Compose

Este módulo implementa la primera pieza operativa de la plataforma del Fixture 2030: la persistencia documental de **64 selecciones** y **1.024 jugadores**, con validación, índices, operaciones CRUD, consultas de recuperación, agregación y análisis de rendimiento.

Todas las decisiones de modelado están justificadas en [`Grupo_8_Hito_4_Decisiones_Documentales_Fixture2030.md`](./Grupo_8_Hito_4_Decisiones_Documentales_Fixture2030.md), en cumplimiento de RNF5 (trazabilidad con los hitos 1, 2 y 3).

---

## 1. Requisitos previos

| Componente | Versión | Cómo verificar |
| --- | --- | --- |
| Docker Desktop (o Docker Engine) | 24+ | `docker version` |
| Docker Compose v2 | 2.x | `docker compose version` |
| bash | 4+ | `bash --version` |
| Python 3 (solo si regenerás los datos) | 3.8+ | `python3 --version` |

No hace falta instalar MongoDB local: todo corre dentro del contenedor.

---

## 2. Estructura del directorio

```
mongodb/
├── docker-compose.yml               # RF1, RF2 (MongoDB 7 + volumen persistente)
├── run-all.sh                       # Orquestador end-to-end
├── init-scripts/
│   └── 01-init-database.js          # RF7 (validaciones JSON Schema + usuario app)
├── data/
│   ├── generar_datos.py             # Generador reproducible (semilla fija)
│   ├── equipos.json                 # 64 equipos (RF4)
│   └── jugadores.json               # 1024 jugadores (RF5)
├── scripts/
│   ├── 01-cargar-datos.js           # RF8 (carga idempotente con upsert)
│   ├── 02-crear-indices.js          # RF12 (índices justificados)
│   ├── 03-operaciones-crud.js       # RF9 (insert + update + validación)
│   ├── 04-consultas.js              # RF10 (ID, filtro, proyección, orden, paginación)
│   ├── 05-agregacion.js             # RF11 (pipelines de agregación)
│   └── 06-analisis-rendimiento.js   # RF12, RNF4 (explain antes/después)
├── evidencia/                       # Logs capturados por run-all.sh
├── Grupo_8_Hito_4_Decisiones_Documentales_Fixture2030.md
└── README.md                        # este archivo
```

---

## 3. Puesta en marcha (una sola línea)

```bash
./run-all.sh
```

El orquestador:
1. Levanta MongoDB en Docker.
2. Espera a que el healthcheck pase.
3. Ejecuta los seis scripts de `scripts/` en orden.
4. Guarda un `.log` por script en `evidencia/`.

Para arrancar **desde cero** (borra volumen + contenedor):

```bash
./run-all.sh reset
```

---

## 4. Puesta en marcha paso a paso (equivalente al script)

```bash
# (1) Levantar MongoDB + Mongo Express
docker compose up -d

# (2) Verificar que MongoDB responde
docker exec fixture2030-mongodb mongosh -u admin -p admin \
  --authenticationDatabase admin --quiet --eval "db.adminCommand('ping')"

# (3) Cargar los 64 equipos y 1024 jugadores (idempotente)
docker exec -i fixture2030-mongodb mongosh -u admin -p admin \
  --authenticationDatabase admin fixture2030 --file /scripts/01-cargar-datos.js

# (4) Crear índices
docker exec -i fixture2030-mongodb mongosh -u admin -p admin \
  --authenticationDatabase admin fixture2030 --file /scripts/02-crear-indices.js

# (5) Operaciones CRUD
docker exec -i fixture2030-mongodb mongosh -u admin -p admin \
  --authenticationDatabase admin fixture2030 --file /scripts/03-operaciones-crud.js

# (6) Consultas de recuperación
docker exec -i fixture2030-mongodb mongosh -u admin -p admin \
  --authenticationDatabase admin fixture2030 --file /scripts/04-consultas.js

# (7) Agregación
docker exec -i fixture2030-mongodb mongosh -u admin -p admin \
  --authenticationDatabase admin fixture2030 --file /scripts/05-agregacion.js

# (8) Análisis de rendimiento (explain con y sin índice)
docker exec -i fixture2030-mongodb mongosh -u admin -p admin \
  --authenticationDatabase admin fixture2030 --file /scripts/06-analisis-rendimiento.js
```

---

## 5. Detener, reiniciar y limpiar

| Objetivo | Comando | Se pierden datos |
| --- | --- | --- |
| Detener sin borrar | `docker compose stop` | No |
| Detener y remover contenedor | `docker compose down` | No (el volumen persiste) |
| Detener y borrar volumen | `docker compose down -v` | **Sí (RF2 desmontado a propósito)** |
| Reiniciar en segundo plano | `docker compose up -d` | No |

---

## 6. Cómo conectarse manualmente

**Desde el host con `mongosh` instalado**:

```bash
mongosh "mongodb://admin:admin@localhost:27017/fixture2030?authSource=admin"
```

**Desde dentro del contenedor** (siempre disponible):

```bash
docker exec -it fixture2030-mongodb mongosh -u admin -p admin --authenticationDatabase admin fixture2030
```

**Interfaz web (Mongo Express)**: [http://localhost:8081](http://localhost:8081) — usuario `admin` / contraseña `admin`.

**Usuarios provisionados**:

| Usuario | Password | Alcance |
| --- | --- | --- |
| `admin` | `admin` | Root del cluster (para administración) |
| `fixture_app` | `fixture_app` | `readWrite` solo sobre `fixture2030` |

> Las credenciales están abiertas a propósito para el ejercicio académico. En producción irían en un secret manager y con roles más granulares.

---

## 7. Regeneración de los datos (opcional)

Los JSON en `data/` ya están versionados. Si querés regenerarlos:

```bash
cd data
python3 generar_datos.py
```

La semilla está fijada en `random.seed(2030)`, así que la salida es idéntica en cada ejecución (RF8, RNF1). Después basta con volver a correr `scripts/01-cargar-datos.js` — el upsert dejará la base consistente sin duplicados.

---

## 8. Cobertura de requisitos

| Req. | Descripción | Dónde se cumple |
| --- | --- | --- |
| RF1 | Entorno local reproducible con Docker Compose | `docker-compose.yml` |
| RF2 | Persistencia de datos ante reinicio | Volumen nombrado `fixture2030_mongo_data` |
| RF3 | Colecciones documentales para equipos y jugadores | `init-scripts/01-init-database.js` |
| RF4 | 64 equipos persistidos | `data/equipos.json` + `scripts/01-cargar-datos.js` |
| RF5 | ≥1.000 jugadores coherentemente vinculados | 1.024 jugadores, `equipoCodigo` valida contra `codigo` del equipo |
| RF6 | Estrategia de relación equipo–jugador documentada | Decisión #1 en `Grupo_8_Hito_4_Decisiones_Documentales_Fixture2030.md` |
| RF7 | Validación de atributos críticos | JSON Schema con `validationAction: "error"` |
| RF8 | Carga reproducible sin duplicados | `bulkWrite` con `updateOne` + `upsert:true` por `codigo` |
| RF9 | Inserción y actualización | `scripts/03-operaciones-crud.js` |
| RF10 | Consultas ID / filtro / proyección / orden / paginación | `scripts/04-consultas.js` |
| RF11 | Al menos una agregación pertinente | `scripts/05-agregacion.js` (cuatro pipelines) |
| RF12 | Índices justificados con evidencia | `scripts/02-crear-indices.js` + `06-analisis-rendimiento.js` |
| RF13 | Evidencia de carga y consultas | Logs generados por `run-all.sh` en `evidencia/` |
| RNF1 | Un tercero levanta el módulo con este README | Instrucciones en este archivo |
| RNF2 | 64 equipos + ≥1.000 jugadores válidos | Verificado por el propio script de carga |
| RNF3 | Sin duplicados ni referencias huérfanas | Verificación explícita al final de `01-cargar-datos.js` |
| RNF4 | Evidencia de planificación de consultas | `explain("executionStats")` en `06-analisis-rendimiento.js` |
| RNF5 | Trazabilidad con hitos previos | Documento de decisiones (secciones 1 y 6) |
| RNF6 | Carga / consultas / docs separadas y nombradas | Directorios `data/`, `scripts/`, `docs/` |
| RNF7 | Portabilidad con Docker Desktop | `docker-compose.yml` estándar, sin dependencias del host |
| RNF8 | Se completa en 90 min de clase | Todos los datos y scripts vienen pre-preparados |

---

## 9. Salida esperada de una ejecución completa

Extractos ilustrativos que produce cada script (verificados con `mongomock` antes de la entrega — ver `evidencia/validacion_local_prerun.log`):

**Carga (`01-cargar-datos.js`)**:
```
[EQUIPOS] insertados=64  actualizados=0  matcheados=0
[JUGADORES] insertados=1024  actualizados=0  matcheados=0
VERIFICACION POST-CARGA:
  equipos.count()   = 64   (esperado 64)
  jugadores.count() = 1024   (esperado >= 1000)
  jugadores huerfanos (equipoCodigo inexistente) = 0   (esperado 0)
```

**Agregación (`05-agregacion.js`)** — Top-10 selecciones por valor de mercado:
```
 1. ARG  Argentina    CONMEBOL  rank=  1  valor=  724.5 MEUR
 2. ESP  Espana       UEFA      rank=  2  valor=  709.1 MEUR
 3. BEL  Belgica      UEFA      rank=  8  valor=  663.1 MEUR
...
```

**Análisis de rendimiento (`06-analisis-rendimiento.js`)**:
```
SIN indice: winning stage = COLLSCAN + SORT, docsExamined = 1024
CON indice: winning stage = IXSCAN,           docsExamined = 16
Reduccion: ~64x
```

---

## 10. Limitaciones conocidas

- **Datos sintéticos**: los nombres de jugadores son generados por script para no reproducir personas reales. Los datos de equipos (código FIFA, nombre, confederación, sede base) son reales y públicos.
- **48 vs 64 selecciones**: el Mundial 2030 se disputa con 48 equipos. El enunciado del Hito 1 fijó 64 registros como supuesto del ejercicio; se respeta ese número.
- **Autenticación abierta**: usuario y clave viven en el `docker-compose.yml` en texto plano; aceptable en el aula, no en producción.
- **Mongo Express opcional**: es una comodidad para inspección visual; si el puerto 8081 está ocupado, comentar el servicio del compose.
- **Consistencia con Neo4j**: el hito 5 (grafos) usará `codigo` FIFA como puente. La política concreta de sincronización se define en ese hito.
- **Sin índices geoespaciales ni de texto**: no forman parte del alcance de este hito; se dejan para etapas donde aparezcan búsquedas por sede geográfica o full-text sobre biografías.
