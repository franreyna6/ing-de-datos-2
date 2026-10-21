# Decisiones de diseño — Módulo de grafos (Hito 5)

**Grupo N.º 8** · Neo4j · Fixture 2030

## 1. Problema relacional

El módulo documental (Hito 4) responde muy bien a "traeme la ficha de este equipo o
jugador", pero se vuelve incómodo cuando la pregunta atraviesa varias entidades. Preguntas del
Fixture 2030 que motivan un grafo:

- ¿En qué sedes se presentó el plantel de una selección a lo largo de sus partidos?
- ¿Quiénes son los goleadores, navegando desde cada gol hasta el jugador y su equipo?
- ¿Qué selecciones quedan conectadas por haber jugado en el mismo estadio, aunque no se hayan enfrentado?
- ¿Cuál es la sede que concentra más partidos (hub logístico)?

Todas exigen **recorrer relaciones** (2 o más saltos). En un modelo documental obligarían a
múltiples consultas y uniones manuales; en un grafo son recorridos naturales.

## 2. Modelo propuesto

Cinco etiquetas de nodo (`Equipo`, `Jugador`, `Partido`, `Sede`, `Evento`) y cinco relaciones
dirigidas (`PERTENECE_A`, `DISPUTA`, `SE_JUEGA_EN`, `OCURRE_EN`, `PROTAGONIZADO_POR`). El detalle
de propiedades, direcciones y cardinalidades está en `modelo_grafo.md`.

## 3. Decisiones de diseño y vínculo con los Hitos 1 a 4

- **Identificadores consistentes (RF5, RNF6).** `Equipo.codigo` y `Jugador.codigo` son los
  mismos del Hito 4 (se leen de `equipos.json` y `jugadores.json`). La misma entidad se reconoce
  en ambos módulos sin integración por código, como pide la consigna.
- **Propiedades mínimas en los nodos.** En el grafo guardamos solo lo identificatorio y lo
  necesario para navegar. Deliberadamente **no** se replican `valorMercado`, `goles`, `altura`,
  etc.: son datos del documento. Esto también atiende la devolución del Hito 3 y del Hito 4 sobre
  **no exceder el alcance** — cada motor cubre lo suyo (principio del Hito 3: información deportiva
  repartida entre documento y grafo).
- **Los goles se modelan como `Evento` (nodo), no como un campo.** En el Hito 4 incluir "goles"
  en el documento fue observado como exceso; en el grafo, el evento es una entidad de primera
  clase que se recorre (gol → jugador → equipo), que es justamente el valor del enfoque.
- **Dirección de las relaciones según la Clase 5.** Se respeta `(Partido)-[:DISPUTA]->(Equipo)` y
  `(Partido)-[:SE_JUEGA_EN]->(Sede)` tal como se presentó en la práctica guiada.
- **Fase de grupos completa.** Se cargan los 64 equipos y 1024 jugadores del Hito 4 y se genera la
  fase de grupos (16 grupos × 6 = 96 partidos) con sus eventos: una muestra coherente con un
  Mundial de 64 equipos y suficiente para validar los recorridos (RF6).

## 4. Datos cargados

Generados de forma reproducible por `generar_fixture.py` (semilla fija) a partir de los datos del
Hito 4. Controles de coherencia verificados antes de escribir los CSV (ver
`evidencia/EVIDENCIA_carga.md`):

| Entidad | Cantidad |
| :--- | :--- |
| Equipo | 64 |
| Jugador | 1024 |
| Sede | 12 |
| Partido | 96 |
| Evento | 437 (365 goles, 72 tarjetas) |

Relaciones esperadas: `PERTENECE_A` 1024, `DISPUTA` 192, `SE_JUEGA_EN` 96, `OCURRE_EN` 437,
`PROTAGONIZADO_POR` 437.

## 5. Consultas

Organizadas en `queries/` por propósito. `crud.cypher` cubre creación, lectura, actualización y
eliminación (RF7) con patrones acotados. `consultas_grafo.cypher` incluye recuperación con
patrón/filtro/orden y **tres recorridos de 2 o más relaciones** (RF8): sedes del plantel (3
saltos), goleadores (2 saltos) y rivales de grupo (2 saltos). El propósito y el resultado esperado
de cada una están comentados en el archivo y evidenciados en `evidencia/`.

## 6. Integridad y rendimiento

- **Unicidad (RF10, RNF4):** restricciones `IS UNIQUE` sobre el `codigo` de cada etiqueta. Además
  de evitar duplicados, crean el índice de respaldo que acelera la búsqueda por `codigo`, que es el
  punto de entrada de casi todas las consultas.
- **Índices de recuperación (RF10):** sobre `Partido.grupo` y `Equipo.confederacion`, que son los
  filtros más frecuentes ("partidos de un grupo", "equipos de una confederación").
- **Idempotencia (RNF4):** toda la carga usa `MERGE`, por lo que re-ejecutarla no crea nodos ni
  relaciones duplicados.

## 7. Análisis relacional (RF9)

Se eligió **centralidad por grado de las sedes** (`consultas_grafo.cypher`, C.1): contar los
partidos que llegan a cada `Sede` por `SE_JUEGA_EN` mide qué estadio es el más central del torneo.
La interpretación en el Fixture es directa: las sedes con mayor grado concentran la carga
logística, de seguridad y de transmisión, y ese ordenamiento no es evidente sin recorrer la
relación partido→sede. Se complementa con una **consulta de conectividad** (C.2/C.3): dos
selecciones que no se enfrentaron pueden quedar vinculadas por compartir estadio, una relación
indirecta que sólo emerge recorriendo el grafo.

> Nota de alcance: el entorno de la Clase 5 habilita APOC y GDS. El análisis requerido se resolvió
> en **Cypher puro** para no depender de proyecciones en memoria ni de la disponibilidad del plugin
> sobre `neo4j:latest`. Con GDS podría extenderse a PageRank o betweenness sobre la red de sedes.

## 8. Limitaciones

- Partidos, sedes y eventos son **generados** (permitido por la consigna); los de equipos y
  jugadores mantienen los identificadores reales del Hito 4.
- Se modeló la **fase de grupos**; las eliminatorias no se incluyen (fuera del alcance mínimo).
- Instancia local única; la réplica/distribución del Hito 3 no se implementa en este hito.
