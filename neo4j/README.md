# Hito 5 — Módulo de Grafos del Fixture 2030 (Neo4j)

**Grupo 8** · Neo4j (`latest`) + Docker Compose

Subgrafo del Fixture 2030 con equipos, jugadores, partidos, sedes y eventos, y las relaciones
que permiten recorrerlos. Un integrante ajeno al desarrollo debe poder levantarlo y repetir la
carga siguiendo estos pasos (RNF3).

## Requisitos previos
- Docker Desktop con `docker compose`.
- Puertos `7474` (Neo4j Browser) y `7687` (Bolt) libres.

## 1. Credenciales (RNF8)
La contraseña se define por variable de entorno. Copiar el ejemplo:
```powershell
Copy-Item .env.example .env      # PowerShell
```
```bash
cp .env.example .env             # bash
```
Valor por defecto (laboratorio, no es un secreto real): usuario `neo4j`, contraseña `fixture2030`.

## 2. Puesta en marcha (RF1)
```
docker compose up -d
docker compose ps
```
- Neo4j Browser: http://localhost:7474  (usuario `neo4j`, contraseña de `.env`)
- Bolt / clientes externos: `neo4j://localhost:7687`
- La primera vez, Neo4j tarda unos segundos en quedar disponible. Verificar con `docker compose logs neo4j`.

## 3. Cargar el grafo
Ejecutar los scripts **en orden**: estructura (constraints) → carga (datos). Los `.cypher` se
pasan a `cypher-shell` dentro del contenedor.

**Windows / PowerShell:**
```powershell
Get-Content .\queries\estructura.cypher | docker exec -i fixture2030-neo4j cypher-shell -u neo4j -p fixture2030
Get-Content .\queries\carga.cypher      | docker exec -i fixture2030-neo4j cypher-shell -u neo4j -p fixture2030
```
**Linux / macOS (bash):**
```bash
docker exec -i fixture2030-neo4j cypher-shell -u neo4j -p fixture2030 < queries/estructura.cypher
docker exec -i fixture2030-neo4j cypher-shell -u neo4j -p fixture2030 < queries/carga.cypher
```
Conteo esperado tras la carga: **equipos=64, jugadores=1024, sedes=12, partidos=96, eventos=437**.

> **Idempotencia (RNF4):** toda la carga usa `MERGE`. Volver a ejecutar `carga.cypher` no crea
> duplicados; los conteos se mantienen.

## 4. Ejecutar CRUD y consultas
```powershell
Get-Content .\queries\crud.cypher            | docker exec -i fixture2030-neo4j cypher-shell -u neo4j -p fixture2030
Get-Content .\queries\consultas_grafo.cypher | docker exec -i fixture2030-neo4j cypher-shell -u neo4j -p fixture2030
```
También pueden pegarse consulta por consulta en Neo4j Browser para ver la **vista de grafo** (RF11).

## 5. Reproducir/regenerar los datos (opcional)
Los CSV de `import/` ya están generados. Para regenerarlos de forma determinista a partir de los
datos del Hito 4:
```
python generar_fixture.py
```

## Estructura del proyecto
```
Grupo_8_Hito_5_Neo4j_Fixture2030/
├── docker-compose.yml            # Neo4j latest + volúmenes + credencial por env
├── .env.example                  # NEO4J_PASSWORD (RNF8)
├── generar_fixture.py            # generación reproducible de los CSV
├── import/                       # CSVs para LOAD CSV
│   ├── equipos.csv  jugadores.csv  sedes.csv
│   ├── partidos.csv  participaciones.csv  eventos.csv
├── queries/
│   ├── estructura.cypher         # constraints + índices (RF10)
│   ├── carga.cypher              # LOAD CSV + MERGE (RF6, RNF4)
│   ├── crud.cypher               # create/read/update/delete acotado (RF7)
│   └── consultas_grafo.cypher    # patrones, recorridos 2+ saltos (RF8) y análisis (RF9)
├── docs/
│   ├── modelo_grafo.md           # etiquetas, relaciones, cardinalidades, diagrama
│   ├── decisiones.md             # análisis y vínculo con Hitos 1-4
│   └── evidencia/                # conteos verificados + plantilla de capturas
└── README.md
```

## Mapa requisito → archivo
| Req. | Dónde |
| :--- | :--- |
| RF1 | `docker-compose.yml`, este README |
| RF2, RF3, RF4 | `docs/modelo_grafo.md`, `queries/carga.cypher` |
| RF5 | identificadores `codigo` del Hito 4 en `import/` |
| RF6 | `generar_fixture.py`, `import/`, `queries/carga.cypher` |
| RF7 | `queries/crud.cypher` |
| RF8 | `queries/consultas_grafo.cypher` (sección B) |
| RF9 | `queries/consultas_grafo.cypher` (sección C), `docs/decisiones.md` §7 |
| RF10 | `queries/estructura.cypher` |
| RF11 | `docs/evidencia/` |

## Nota sobre `neo4j:latest` (RNF1)
El Compose usa `neo4j:latest` según el criterio de la materia.
- **Fecha de prueba del entorno:** 17/09/2026. Se verificó ejecutando
  `docker exec fixture2030-neo4j neo4j --version`, que devolvió `2026.08.1`.
- El Compose habilita los plugins APOC y GDS (como el entorno de la Clase 5). **Las consultas
  requeridas no dependen de ellos.** Si una versión `latest` fuera incompatible y el contenedor no
  arrancara, quitar la línea `NEO4J_PLUGINS` del Compose y volver a levantar: el módulo funciona
  igual. Registrar la incidencia aquí si ocurre.

## Limitaciones conocidas
- Partidos, sedes y eventos son datos **generados** (permitido); equipos y jugadores conservan los
  identificadores reales del Hito 4.
- Se modeló la **fase de grupos** (96 partidos); las eliminatorias quedan fuera del alcance.
- Instancia local única; la réplica/distribución del Hito 3 no se implementa en este hito.
