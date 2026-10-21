# Evidencia de carga e integridad del subgrafo

Valores **verificados sobre los CSV generados** (`generar_fixture.py`, semilla fija) antes de
cargarlos en Neo4j. Al ejecutar `carga.cypher`, los conteos deben coincidir.

## Conteos de nodos

| Nodo | Cantidad | Requisito |
| :--- | :--- | :--- |
| Equipo | **64** | RF6 (= 64) |
| Jugador | **1024** | RF6 (≥ 1000) |
| Sede | 12 | muestra de estadios |
| Partido | 96 | fase de grupos (16×6) |
| Evento | 437 | 365 goles + 72 tarjetas |

## Conteos de relaciones

| Relación | Cantidad |
| :--- | :--- |
| `PERTENECE_A` | 1024 |
| `DISPUTA` | 192 |
| `SE_JUEGA_EN` | 96 |
| `OCURRE_EN` | 437 |
| `PROTAGONIZADO_POR` | 437 |

## Verificación de integridad (previa a la carga)

| Chequeo | Resultado |
| :--- | :--- |
| 64 equipos / ≥1000 jugadores | ✅ |
| 16 grupos de 4 equipos | ✅ |
| Todo jugador referencia un equipo válido | ✅ |
| Cada partido tiene exactamente 2 participaciones | ✅ |
| Los dos rivales de un partido son del mismo grupo | ✅ |
| Todo partido referencia una sede válida | ✅ |
| Todo evento referencia un partido válido | ✅ |
| Todo evento referencia un jugador válido | ✅ |
| Sin códigos de partido / evento duplicados | ✅ |

## Cómo verificar en Neo4j tras la carga

```cypher
// Conteo de nodos por etiqueta
MATCH (e:Equipo)  RETURN 'Equipo'  AS nodo, count(e) AS n
UNION ALL MATCH (j:Jugador) RETURN 'Jugador', count(j)
UNION ALL MATCH (s:Sede)    RETURN 'Sede', count(s)
UNION ALL MATCH (p:Partido) RETURN 'Partido', count(p)
UNION ALL MATCH (v:Evento)  RETURN 'Evento', count(v);

// Idempotencia: volver a correr carga.cypher y confirmar que estos conteos NO cambian.

// Integridad referencial: partidos que no tengan exactamente 2 equipos (debe dar 0 filas)
MATCH (p:Partido)
WITH p, count { (p)-[:DISPUTA]->(:Equipo) } AS equipos
WHERE equipos <> 2
RETURN p.codigo, equipos;
```

> Las capturas de Neo4j Browser (carga, consultas y visualización del subgrafo, RF11) van en esta carpeta.
