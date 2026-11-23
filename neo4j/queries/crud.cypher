// =============================================================================
// crud.cypher  —  Operaciones CRUD sobre nodos y relaciones (RF7)
// -----------------------------------------------------------------------------
// Cada bloque declara su proposito. Las eliminaciones usan patrones ACOTADOS
// (nunca un DELETE sin filtro): una instruccion de borrado amplia puede eliminar
// el subgrafo completo. Se opera sobre datos de prueba para no tocar el fixture.
// =============================================================================

// --- CREATE -------------------------------------------------------------------
// Alta de un evento nuevo (una asistencia) vinculado a un partido y a un jugador
// existentes. Se usa MERGE para que repetir el alta no duplique (RNF4).
MERGE (v:Evento {codigo: 'EV-TEST-1'})
SET v.tipo = 'Asistencia', v.minuto = 55
WITH v
MATCH (p:Partido {codigo: 'F2030-001'})
MATCH (j:Jugador {codigo: 'ARG-10-emtxem'})
MERGE (v)-[:OCURRE_EN]->(p)
MERGE (v)-[:PROTAGONIZADO_POR]->(j)
RETURN v.codigo AS evento, v.tipo AS tipo;

// --- READ ---------------------------------------------------------------------
// Recuperar el evento recien creado y el contexto al que quedo vinculado.
MATCH (v:Evento {codigo: 'EV-TEST-1'})-[:OCURRE_EN]->(p:Partido)
MATCH (v)-[:PROTAGONIZADO_POR]->(j:Jugador)
RETURN v.codigo AS evento, v.tipo AS tipo, p.codigo AS partido, j.nombre AS jugador;

// --- UPDATE -------------------------------------------------------------------
// Corregir el minuto del evento (patron preciso por codigo).
MATCH (v:Evento {codigo: 'EV-TEST-1'})
SET v.minuto = 60
RETURN v.codigo AS evento, v.minuto AS minutoActualizado;

// Actualizar una propiedad de relacion: registrar el resultado de cada equipo
// en su participacion (DISPUTA), calculado a partir de los goles del partido.
// Patron acotado a un partido. Devuelve el valor antes y despues del SET para
// que la evidencia muestre la modificacion. Es idempotente: repetirlo deja el
// mismo valor.
MATCH (p:Partido {codigo: 'F2030-001'})-[d:DISPUTA]->(e:Equipo)
WITH p, d, e, d.resultado AS antes
SET d.resultado = CASE
      WHEN p.golesLocal = p.golesVisitante THEN 'empate'
      WHEN (d.condicion = 'local'     AND p.golesLocal     > p.golesVisitante)
        OR (d.condicion = 'visitante' AND p.golesVisitante > p.golesLocal) THEN 'victoria'
      ELSE 'derrota'
    END
RETURN p.codigo AS partido, e.codigo AS equipo, d.condicion AS condicion,
       antes, d.resultado AS despues;

// --- DELETE (acotado) ---------------------------------------------------------
// Eliminar SOLO una relacion puntual del evento de prueba.
MATCH (v:Evento {codigo: 'EV-TEST-1'})-[r:PROTAGONIZADO_POR]->(:Jugador)
DELETE r;

// Eliminar el nodo de prueba y sus relaciones restantes (DETACH DELETE acotado
// por codigo: nunca sin filtro).
MATCH (v:Evento {codigo: 'EV-TEST-1'})
DETACH DELETE v;

// Verificacion: el evento de prueba ya no existe (debe devolver 0 filas).
MATCH (v:Evento {codigo: 'EV-TEST-1'})
RETURN v;
