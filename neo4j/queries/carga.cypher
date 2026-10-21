// =============================================================================
// carga.cypher  —  Carga reproducible e idempotente del subgrafo (RF6, RNF4)
// -----------------------------------------------------------------------------
// Fuente: CSVs en ./import (montados en /var/lib/neo4j/import).
// Mecanismo: LOAD CSV + MERGE. MERGE crea el nodo/relacion solo si no existe,
// por lo que re-ejecutar esta carga NO genera duplicados (RNF4).
// Requiere haber corrido antes estructura.cypher (constraints).
// =============================================================================

// --- 1) EQUIPOS ---------------------------------------------------------------
// Se conserva el 'codigo' del Hito 4 (RF5). Propiedades minimas: la ficha
// completa vive en el modulo documental; el grafo guarda solo lo identificatorio
// y lo necesario para navegar (decision de diseno, ver docs/decisiones.md).
LOAD CSV WITH HEADERS FROM 'file:///equipos.csv' AS row
MERGE (e:Equipo {codigo: row.codigo})
SET e.nombre        = row.nombre,
    e.confederacion = row.confederacion,
    e.rankingFIFA   = toInteger(row.rankingFIFA),
    e.esAnfitrion   = (row.esAnfitrion = 'true'),
    e.grupo         = row.grupo;

// --- 2) JUGADORES + relacion PERTENECE_A -------------------------------------
LOAD CSV WITH HEADERS FROM 'file:///jugadores.csv' AS row
MERGE (j:Jugador {codigo: row.codigo})
SET j.nombre   = row.nombre,
    j.posicion = row.posicion,
    j.dorsal   = toInteger(row.dorsal)
WITH j, row
MATCH (e:Equipo {codigo: row.equipoCodigo})
MERGE (j)-[:PERTENECE_A]->(e);

// --- 3) SEDES -----------------------------------------------------------------
LOAD CSV WITH HEADERS FROM 'file:///sedes.csv' AS row
MERGE (s:Sede {codigo: row.codigo})
SET s.nombre = row.nombre,
    s.ciudad = row.ciudad,
    s.pais   = row.pais;

// --- 4) PARTIDOS + relacion SE_JUEGA_EN --------------------------------------
LOAD CSV WITH HEADERS FROM 'file:///partidos.csv' AS row
MERGE (p:Partido {codigo: row.codigo})
SET p.fecha          = date(row.fecha),
    p.fase           = row.fase,
    p.grupo          = row.grupo,
    p.golesLocal     = toInteger(row.golesLocal),
    p.golesVisitante = toInteger(row.golesVisitante)
WITH p, row
MATCH (s:Sede {codigo: row.sedeCodigo})
MERGE (p)-[:SE_JUEGA_EN]->(s);

// --- 5) PARTICIPACIONES: relacion DISPUTA (partido -> equipo) ----------------
// Direccion segun la convencion de la Clase 5: (Partido)-[:DISPUTA]->(Equipo).
// La condicion (local/visitante) se guarda como propiedad de la relacion.
LOAD CSV WITH HEADERS FROM 'file:///participaciones.csv' AS row
MATCH (p:Partido {codigo: row.partidoCodigo})
MATCH (e:Equipo  {codigo: row.equipoCodigo})
MERGE (p)-[d:DISPUTA]->(e)
SET d.condicion = row.condicion;

// --- 6) EVENTOS + OCURRE_EN (evento->partido) + PROTAGONIZADO_POR (evento->jugador)
LOAD CSV WITH HEADERS FROM 'file:///eventos.csv' AS row
MERGE (v:Evento {codigo: row.codigo})
SET v.tipo   = row.tipo,
    v.minuto = toInteger(row.minuto)
WITH v, row
MATCH (p:Partido {codigo: row.partidoCodigo})
MERGE (v)-[:OCURRE_EN]->(p)
WITH v, row
MATCH (j:Jugador {codigo: row.jugadorCodigo})
MERGE (v)-[:PROTAGONIZADO_POR]->(j);

// --- 7) Verificacion post-carga (RNF7) ---------------------------------------
MATCH (e:Equipo)   WITH count(e) AS equipos
MATCH (j:Jugador)  WITH equipos, count(j) AS jugadores
MATCH (s:Sede)     WITH equipos, jugadores, count(s) AS sedes
MATCH (p:Partido)  WITH equipos, jugadores, sedes, count(p) AS partidos
MATCH (v:Evento)   WITH equipos, jugadores, sedes, partidos, count(v) AS eventos
RETURN equipos, jugadores, sedes, partidos, eventos;
// Esperado: equipos=64, jugadores=1024, sedes=12, partidos=96, eventos=437.
