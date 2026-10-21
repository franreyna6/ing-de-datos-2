// =============================================================================
// consultas_grafo.cypher  —  Consultas de patrones, recorridos y analisis
// -----------------------------------------------------------------------------
// Organizadas por proposito (RNF5). Cada consulta indica su objetivo funcional
// y es verificable contra los datos cargados (RNF7).
//   A) Recuperacion con patron, filtro y orden
//   B) Recorridos de 2 o mas relaciones consecutivas (RF8)
//   C) Analisis del grafo: centralidad y conectividad (RF9)
// =============================================================================


// =========================== A) PATRON / FILTRO / ORDEN ======================

// A.1) Plantel de una seleccion (1 relacion, ordenado por dorsal).
// Objetivo: ficha de plantel de Argentina.
MATCH (j:Jugador)-[:PERTENECE_A]->(:Equipo {codigo: 'ARG'})
RETURN j.dorsal AS dorsal, j.nombre AS jugador, j.posicion AS posicion
ORDER BY dorsal;

// A.2) Partidos de un grupo con su sede (filtro por la propiedad indexada 'grupo').
// Objetivo: programacion del Grupo A.
MATCH (p:Partido {grupo: 'A'})-[:SE_JUEGA_EN]->(s:Sede)
RETURN p.codigo AS partido, p.fecha AS fecha, s.nombre AS sede,
       p.golesLocal AS gl, p.golesVisitante AS gv
ORDER BY p.fecha;


// =================== B) RECORRIDOS DE 2+ RELACIONES (RF8) =====================

// B.1) [4 relaciones] Goles con su autor, seleccion, partido y sede.
// Recorrido: (Evento{Gol})->PROTAGONIZADO_POR->(Jugador)->PERTENECE_A->(Equipo)
//            y (Evento)->OCURRE_EN->(Partido)->SE_JUEGA_EN->(Sede)
// Objetivo: cronica de goles cruzando cuatro relaciones del grafo.
MATCH (v:Evento {tipo: 'Gol'})-[:PROTAGONIZADO_POR]->(j:Jugador)-[:PERTENECE_A]->(e:Equipo)
MATCH (v)-[:OCURRE_EN]->(p:Partido)-[:SE_JUEGA_EN]->(s:Sede)
RETURN j.nombre AS goleador, e.nombre AS seleccion,
       p.codigo AS partido, s.nombre AS sede, v.minuto AS minuto
ORDER BY partido, minuto
LIMIT 15;

// B.2) [2 relaciones] Maximos goleadores del torneo.
// Recorrido: (Evento{Gol})->PROTAGONIZADO_POR->(Jugador)->PERTENECE_A->(Equipo)
// Objetivo: tabla de goleadores navegando eventos, no un campo agregado.
MATCH (v:Evento {tipo: 'Gol'})-[:PROTAGONIZADO_POR]->(j:Jugador)-[:PERTENECE_A]->(e:Equipo)
RETURN j.nombre AS jugador, e.nombre AS seleccion, count(v) AS goles
ORDER BY goles DESC, jugador
LIMIT 10;

// B.3) [2 relaciones] Rivales de una seleccion en la fase de grupos.
// Recorrido: (Partido)->DISPUTA->(ARG) y el mismo (Partido)->DISPUTA->(rival)
// Objetivo: fixture de Argentina.
MATCH (p:Partido)-[:DISPUTA]->(arg:Equipo {codigo: 'ARG'})
MATCH (p)-[:DISPUTA]->(rival:Equipo)
WHERE rival.codigo <> 'ARG'
RETURN p.codigo AS partido, p.fecha AS fecha, rival.nombre AS rival
ORDER BY p.fecha;


// =================== C) ANALISIS DEL GRAFO (RF9) =============================

// C.1) CENTRALIDAD POR GRADO de las sedes.
// Objetivo: identificar la sede "hub" del torneo (la que concentra mas partidos).
// El grado de entrada de cada Sede por SE_JUEGA_EN es una medida de centralidad
// calculable en Cypher puro.
// Interpretacion: las sedes con mayor grado son criticas para logistica,
// seguridad y transmision; no surge de una tabla de partidos sin recorrer la
// relacion partido->sede.
MATCH (s:Sede)<-[:SE_JUEGA_EN]-(p:Partido)
RETURN s.nombre AS sede, s.ciudad AS ciudad, s.pais AS pais,
       count(p) AS gradoPartidos
ORDER BY gradoPartidos DESC, sede;

// C.2) CONECTIVIDAD: selecciones vinculadas a Argentina por sede compartida.
// Recorrido de camino: (ARG)<-DISPUTA-(Partido)->SE_JUEGA_EN->(Sede)<-SE_JUEGA_EN-(Partido)->DISPUTA->(otro)
// Objetivo: descubrir equipos vinculados a Argentina por haber jugado en el mismo
// estadio, aunque no se hayan enfrentado.
// Interpretacion: relacion indirecta de infraestructura que una consulta de
// enfrentamientos directos no revelaria.
MATCH (arg:Equipo {codigo: 'ARG'})<-[:DISPUTA]-(:Partido)-[:SE_JUEGA_EN]->(s:Sede)
      <-[:SE_JUEGA_EN]-(:Partido)-[:DISPUTA]->(otro:Equipo)
WHERE otro.codigo <> 'ARG'
RETURN DISTINCT otro.nombre AS equipoConectado, s.nombre AS sedeCompartida
ORDER BY equipoConectado
LIMIT 15;
