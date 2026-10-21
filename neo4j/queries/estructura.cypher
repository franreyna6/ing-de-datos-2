// =============================================================================
// estructura.cypher  —  Restricciones de integridad e indices (RF10)
// -----------------------------------------------------------------------------
// Se ejecuta ANTES de la carga. Las restricciones de unicidad garantizan que no
// existan nodos duplicados por identificador y, ademas, crean un indice de
// respaldo que acelera las busquedas por 'codigo' (el patron mas frecuente).
// Todas usan IF NOT EXISTS -> son idempotentes (RNF4).
// =============================================================================

// --- Unicidad de identificadores (RF10, RNF4) --------------------------------
// Los 'codigo' de equipo y jugador son los MISMOS del Hito 4 (RF5): la unicidad
// preserva la correspondencia 1:1 entre el nodo del grafo y el documento de Mongo.
CREATE CONSTRAINT equipo_codigo   IF NOT EXISTS FOR (e:Equipo)  REQUIRE e.codigo IS UNIQUE;
CREATE CONSTRAINT jugador_codigo  IF NOT EXISTS FOR (j:Jugador) REQUIRE j.codigo IS UNIQUE;
CREATE CONSTRAINT partido_codigo  IF NOT EXISTS FOR (p:Partido) REQUIRE p.codigo IS UNIQUE;
CREATE CONSTRAINT sede_codigo     IF NOT EXISTS FOR (s:Sede)    REQUIRE s.codigo IS UNIQUE;
CREATE CONSTRAINT evento_codigo   IF NOT EXISTS FOR (v:Evento)  REQUIRE v.codigo IS UNIQUE;

// --- Indices para recuperaciones frecuentes (RF10) ---------------------------
// Filtro habitual "partidos de un grupo" y "equipos de una confederacion".
CREATE INDEX partido_grupo        IF NOT EXISTS FOR (p:Partido) ON (p.grupo);
CREATE INDEX equipo_confederacion IF NOT EXISTS FOR (e:Equipo)  ON (e.confederacion);

// Verificacion
SHOW CONSTRAINTS;
SHOW INDEXES;
