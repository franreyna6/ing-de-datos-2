# Hito 6 — Comentarios masivos del Fixture 2030 (Cassandra)

**Grupo 8** · Apache Cassandra (`latest`) + Docker Compose

Módulo de comentarios de partidos: publicar muchos mensajes por segundo y recuperar el feed de un
partido y el historial de un usuario. El diseño parte de las consultas (no de un diagrama
de entidades) y reparte los partidos populares en ventanas de tiempo. Un integrante ajeno al
desarrollo debe poder levantarlo y repetir la carga siguiendo estos pasos (RNF3).

## Requisitos previos
- Docker Desktop con `docker compose`.
- Puerto `9042` (CQL) libre.
- Python 3 (solo para generar el volumen masivo; usa solo la biblioteca estándar).
- Memoria suficiente para Docker (Cassandra es exigente; si el contenedor se reinicia, subir la
  memoria asignada a Docker Desktop).

## 1. Puesta en marcha (RF1)
```
docker compose up -d
docker compose ps
docker compose logs -f cassandra
```
El primer inicio descarga `cassandra:latest` y tarda; no ejecutar CQL hasta que `docker compose ps`
muestre el contenedor como *healthy* y el log indique que el servicio está listo. Los datos
persisten en `~/docker/data/cassandra` (RNF2).

> Si Compose no expande `~` en tu sistema, reemplazar esa ruta en `docker-compose.yml` por la ruta
> absoluta de tu carpeta personal.

Verificar el nodo con las herramientas del contenedor:
```
docker exec -it fixture2030-cassandra nodetool status      # estado UN = Up/Normal
docker exec -it fixture2030-cassandra cqlsh                # cliente CQL interactivo
```

## 2. Esquema, muestra, CRUD y consultas
Los scripts se ejecutan **en este orden** con `cqlsh -f` dentro del contenedor (los comandos son
iguales en Windows, macOS y Linux):
```
docker exec -i fixture2030-cassandra cqlsh -f /scripts/esquema.cql
docker exec -i fixture2030-cassandra cqlsh -f /scripts/carga_muestra.cql
docker exec -i fixture2030-cassandra cqlsh -f /scripts/crud.cql
docker exec -i fixture2030-cassandra cqlsh -f /scripts/consultas.cql
```
O bien todo junto, guardando la evidencia en `docs/evidencia/logs/`:
```
bash scripts/ejecutar_todo.sh                                              # Linux / macOS / Git Bash
powershell -ExecutionPolicy Bypass -File .\scripts\ejecutar_todo.ps1       # Windows
```
> En Git Bash (Windows), si un comando con `/scripts/...` falla por conversión de rutas, anteponer
> `MSYS_NO_PATHCONV=1`.

> **Idempotencia (RNF7):** `esquema.cql` usa `IF NOT EXISTS` y las cargas son *upserts* con
> identificadores fijos. Repetir cualquier paso no duplica datos.

## 3. Carga masiva (1.100.000 comentarios, más de 1.000.000) y medición (RF11, RF12)
```
python scripts/generar_datos.py              # genera data/generado/*.csv (1.100.000 filas, ≈ 30 s)
bash scripts/carga_o_prueba.sh               # COPY de ambos CSV + medición + verificación
```
Windows: `powershell -ExecutionPolicy Bypass -File .\scripts\carga_o_prueba.ps1`.
Para validar el flujo primero con poco volumen: `TOTAL=20000 bash scripts/carga_o_prueba.sh`
(en PowerShell: `$env:TOTAL = 20000`). El log queda en `docs/evidencia/logs/carga_<fecha>.log`.
Detalle del método y de cómo interpretar la tasa: `docs/rendimiento.md`.

## 4. Reiniciar desde cero (solo si se quiere)
```
docker compose down
```
y eliminar manualmente `~/docker/data/cassandra` **únicamente** con esa intención explícita.

## Estructura del proyecto
```
cassandra/
├── docker-compose.yml               # Cassandra latest + persistencia + scripts y datos montados
├── scripts/
│   ├── esquema.cql                  # keyspace + tablas (RF2, RF4-RF7, RF10)
│   ├── carga_muestra.cql            # muestra funcional de 13 comentarios (RF11)
│   ├── crud.cql                     # create / read / update / delete (RF8)
│   ├── consultas.cql                # consultas P1-P4 y TRACING (RF9)
│   ├── generar_datos.py             # generador reproducible del volumen masivo (RF11)
│   ├── carga_o_prueba.sh / .ps1     # COPY + medición de escrituras (RF12)
│   └── ejecutar_todo.sh / .ps1      # esquema -> muestra -> CRUD -> consultas con logs (RF13)
├── data/
│   ├── origen/                      # CSV del Hito 5 (partidos, equipos, participaciones, eventos)
│   └── generado/                    # CSV del volumen masivo (no versionado)
├── docs/
│   ├── patrones_de_acceso.md        # problema de volumen + patrones de lectura y escritura
│   ├── modelo_tabular.md            # tablas, claves, estructura secundaria, operaciones CQL
│   ├── decisiones_de_particionamiento.md  # partición, bucket, duplicación, réplicas, coherencia
│   ├── datos_cargados.md            # origen, reglas y distribución de los datos
│   ├── rendimiento.md               # método de medición, resultados, límites y mejoras
│   └── evidencia/                   # distribución generada + logs de ejecución
└── README.md
```

## Mapa requisito → archivo
| Req. | Dónde |
| :--- | :--- |
| RF1 | `docker-compose.yml`, este README (§1) |
| RF2 | `scripts/esquema.cql`, `docs/modelo_tabular.md` §1 |
| RF3 | `docs/patrones_de_acceso.md` |
| RF4, RF5, RF6 | `scripts/esquema.cql`, `docs/modelo_tabular.md` §2 |
| RF7 | `docs/decisiones_de_particionamiento.md` §1–§4 |
| RF8 | `scripts/crud.cql` |
| RF9 | `scripts/consultas.cql` |
| RF10 | `comentarios_por_usuario` en `scripts/esquema.cql`, `docs/modelo_tabular.md` §2.2 |
| RF11 | `scripts/carga_muestra.cql`, `scripts/generar_datos.py`, `docs/datos_cargados.md` |
| RF12 | `scripts/carga_o_prueba.*`, `docs/rendimiento.md` |
| RF13 | `docs/evidencia/` |
| RNF1 | `docker-compose.yml` (`cassandra:latest`) |
| RNF2 | `docker-compose.yml` (`~/docker/data/cassandra`) |
| RNF3 | este README |
| RNF4 | `docs/modelo_tabular.md` §3 |
| RNF5 | `docs/decisiones_de_particionamiento.md` §1–§4 |
| RNF6 | comentarios y secciones de cada `.cql` |
| RNF7 | `IF NOT EXISTS`, ids fijos y deterministas |
| RNF8 | nodo local sin credenciales reales, declarado como ambiente de laboratorio |
| RNF9 | `SHOW VERSION` en `esquema.cql` y en el log de carga |

## Nota sobre `cassandra:latest` (RNF1, RNF9)
El Compose usa `cassandra:latest` según el criterio de la materia. Cada prueba debe registrar la
**fecha** y la **versión** que informa `SHOW VERSION` (lo hacen `esquema.cql` y
`carga_o_prueba.*`, y queda en `docs/evidencia/logs/`). Registro de este grupo:

- Fecha de prueba del entorno: 02/10/2026 (hora de Argentina; 2026-10-03 ≈ 00:30 UTC).
- Versión observada (`SHOW VERSION`): `cqlsh 6.2.0 | Cassandra 5.0.9 | CQL spec 3.4.7 | Native protocol v5`.
- Resultado de la carga de 1.100.000 de comentarios (2.200.000 de escrituras físicas): 100,1 s,
  ≈ 21.977 escrituras/s con `COPY` (`NUMPROCESSES=2`) en un nodo único. Detalle, ambiente y
  límites en `docs/rendimiento.md`; registro completo en
  `docs/evidencia/logs/carga_20261003_002948.log`.

## Limitaciones conocidas
- **Nodo único, `SimpleStrategy`, factor de replicación 1.** Es un laboratorio de aprendizaje: no
  demuestra alta disponibilidad ni multirregión (`docs/decisiones_de_particionamiento.md` §6).
- Los comentarios y los usuarios son **sintéticos**; los partidos, fechas, goles y tarjetas son los
  del Hito 5.
- Las tasas de escritura se miden con `COPY` (cliente `cqlsh`) y dependen de la notebook; ver
  `docs/rendimiento.md`.
- La cola de moderación y los reportes analíticos no se resuelven con este modelo
  (`docs/patrones_de_acceso.md` §2.3).
