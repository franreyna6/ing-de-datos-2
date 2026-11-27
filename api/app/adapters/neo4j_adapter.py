"""Adaptador de grafos: Neo4j (Hito 5) — partidos, eventos y participantes.

Unico lugar que conoce el driver Bolt de Neo4j (RNF5). El Cypher es FIJO y
parametrizado: los valores del cliente entran como parametros ($codigo), nunca
se concatenan dentro de la consulta (previene inyeccion; la clase lo marca en
rojo). El consumidor no puede enviar Cypher ni nombres de etiquetas/relaciones.

Modelo del Hito 5 (convencion de la Clase 5):
  (Partido)-[:DISPUTA]->(Equipo)        participacion equipo-partido
  (Partido)-[:SE_JUEGA_EN]->(Sede)
  (Evento)-[:OCURRE_EN]->(Partido)
  (Evento)-[:PROTAGONIZADO_POR]->(Jugador)
"""
from __future__ import annotations

from app.core.config import obtener_config
from app.core.errores import ErrorDependencia
from app.core.registro import logger

FUENTE = "neo4j"

# Eventos conectados a un partido (RF4). Cypher parametrizado y acotado con LIMIT.
_CYPHER_EVENTOS = """
MATCH (p:Partido {codigo: $codigo})
OPTIONAL MATCH (ev:Evento)-[:OCURRE_EN]->(p)
OPTIONAL MATCH (ev)-[:PROTAGONIZADO_POR]->(j:Jugador)
RETURN p.codigo AS partido, p.fecha AS fecha,
       ev.codigo AS evento, ev.tipo AS tipo, ev.minuto AS minuto,
       j.codigo AS jugador_codigo, j.nombre AS jugador_nombre
ORDER BY minuto
LIMIT $limit
"""

# Solo para distinguir "partido inexistente" de "partido sin eventos" (RF4).
_CYPHER_EXISTE = "MATCH (p:Partido {codigo: $codigo}) RETURN p.codigo AS codigo LIMIT 1"


class Neo4jAdapter:
    def __init__(self) -> None:
        self._cfg = obtener_config()
        self._driver = None

    def _obtener_driver(self):
        if self._driver is None:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(
                self._cfg.neo4j_uri,
                auth=(self._cfg.neo4j_user, self._cfg.neo4j_password),
                connection_timeout=self._cfg.dep_timeout_s,
            )
        return self._driver

    def verificar(self) -> bool:
        try:
            self._obtener_driver().verify_connectivity()
            return True
        except Exception:
            return False

    def eventos_de_partido(self, codigo: str, limit: int) -> dict | None:
        """Devuelve {partido, eventos:[...]} o None si el partido no existe.

        Un partido valido sin eventos devuelve la lista vacia (no es un 404).
        """
        try:
            with self._obtener_driver().session(database=self._cfg.neo4j_database) as ses:
                existe = ses.run(_CYPHER_EXISTE, codigo=codigo).single()
                if existe is None:
                    logger.info("neo4j partido=%s inexistente", codigo)
                    return None
                registros = ses.run(_CYPHER_EVENTOS, codigo=codigo, limit=limit)
                eventos = []
                partido_fecha = None
                for r in registros:
                    partido_fecha = r.get("fecha")
                    if r.get("evento") is None:
                        continue  # partido sin eventos (OPTIONAL MATCH)
                    eventos.append({
                        "evento": r.get("evento"),
                        "tipo": r.get("tipo"),
                        "minuto": r.get("minuto"),
                        "jugadorCodigo": r.get("jugador_codigo"),
                        "jugadorNombre": r.get("jugador_nombre"),
                    })
        except ErrorDependencia:
            raise
        except Exception as e:
            logger.warning("neo4j error partido=%s", codigo)
            raise ErrorDependencia(FUENTE, str(e))
        logger.info("neo4j partido=%s eventos=%s", codigo, len(eventos))
        return {"partido": codigo, "fecha": str(partido_fecha) if partido_fecha else None,
                "eventos": eventos}

    # ------------------------------------------- Hito 13: demo en vivo (escritura)
    # Solo se escribe sobre partidos de LABORATORIO (H13-DEMO-...), marcados con
    # laboratorio=true: la demo nunca modifica el fixture real (RNF5 del Hito 13).
    # El servicio valida el prefijo antes de llegar aca.
    def crear_partido_lab(self, codigo: str, fecha: str, fase: str, local: str,
                          visitante: str, sede: str) -> dict | None:
        """Crea (o recrea limpio) el partido de laboratorio y sus relaciones."""
        try:
            with self._obtener_driver().session(database=self._cfg.neo4j_database) as ses:
                # El context manager hace rollback si no se llega al commit.
                with ses.begin_transaction() as tx:
                    # 1. Si quedo de una corrida anterior: borrar sus eventos y relaciones.
                    tx.run("MATCH (ev:Evento)-[:OCURRE_EN]->(p:Partido {codigo: $c}) "
                           "WHERE p.laboratorio = true DETACH DELETE ev", c=codigo)
                    tx.run("MATCH (p:Partido {codigo: $c})-[r:DISPUTA|SE_JUEGA_EN]->() "
                           "WHERE p.laboratorio = true DELETE r", c=codigo)
                    # 2. Partido + participaciones + sede (mismo modelo del Hito 5).
                    fila = tx.run(
                        "MATCH (l:Equipo {codigo: $local}), (v:Equipo {codigo: $visitante}), "
                        "      (s:Sede {codigo: $sede}) "
                        "MERGE (p:Partido {codigo: $c}) "
                        "SET p.fecha = $fecha, p.fase = $fase, p.golesLocal = 0, "
                        "    p.golesVisitante = 0, p.laboratorio = true "
                        "MERGE (p)-[dl:DISPUTA]->(l) SET dl.condicion = 'local' "
                        "MERGE (p)-[dv:DISPUTA]->(v) SET dv.condicion = 'visitante' "
                        "MERGE (p)-[:SE_JUEGA_EN]->(s) "
                        "RETURN p.codigo AS codigo, l.nombre AS local, v.nombre AS visitante, "
                        "       s.nombre AS sede, s.ciudad AS ciudad",
                        c=codigo, fecha=fecha, fase=fase, local=local,
                        visitante=visitante, sede=sede).single()
                    if fila is None:
                        return None  # equipo o sede inexistente -> 404 (rollback)
                    tx.commit()
                    return dict(fila)
        except Exception as e:
            logger.warning("neo4j error crear partido lab=%s", codigo)
            raise ErrorDependencia(FUENTE, str(e))

    def registrar_evento(self, partido: str, evento: str, tipo: str, minuto: int,
                         jugador: str, goles_local: int, goles_visitante: int) -> dict | None:
        """Agrega el evento como NODO conectado al partido y al jugador.

        MERGE por codigo: si la API reintenta, no se duplica el gol. El marcador
        se copia del que valido IRIS (fuente de verdad del estado del partido).
        """
        cypher = (
            "MATCH (p:Partido {codigo: $p}) WHERE p.laboratorio = true "
            "MATCH (j:Jugador {codigo: $j})-[:PERTENECE_A]->(e:Equipo) "
            "MERGE (ev:Evento {codigo: $ev}) "
            "ON CREATE SET ev.tipo = $tipo, ev.minuto = $minuto, ev.laboratorio = true "
            "MERGE (ev)-[:OCURRE_EN]->(p) "
            "MERGE (ev)-[:PROTAGONIZADO_POR]->(j) "
            "SET p.golesLocal = $gl, p.golesVisitante = $gv "
            "RETURN ev.codigo AS evento, j.nombre AS jugador, e.codigo AS equipo")
        try:
            with self._obtener_driver().session(database=self._cfg.neo4j_database) as ses:
                fila = ses.execute_write(lambda tx: tx.run(
                    cypher, p=partido, j=jugador, ev=evento, tipo=tipo, minuto=minuto,
                    gl=goles_local, gv=goles_visitante).single())
        except Exception as e:
            logger.warning("neo4j error registrar evento partido=%s", partido)
            raise ErrorDependencia(FUENTE, str(e))
        return dict(fila) if fila else None

    def cerrar(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None


neo4j_adapter = Neo4jAdapter()
