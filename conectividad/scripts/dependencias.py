"""Mapa de dependencias de la API del Hito 10, derivado de la configuracion (RF1).

Es la version ejecutable de docs/mapa_de_dependencias.md: para cada producto
indica que endpoints (host, puerto, protocolo) usa el proceso de la API, que
contexto selecciona, que variables lo configuran y que rutas de la API lo usan.
Los scripts de prueba recorren este mapa en lugar de repetir hosts y puertos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from lib_conectividad import Config


@dataclass
class Endpoint:
    rol: str          # "driver de la API", "portal HTTP", ...
    host: str
    puerto: int
    protocolo: str
    usado_por_api: bool


@dataclass
class Dependencia:
    producto: str
    modulo: str
    hito: str
    contexto: str
    autenticacion: str
    cliente_api: str
    cliente_nativo: str
    contenedor: str
    variables: list[str]
    obligatorias: list[str]
    rutas_api: list[str]
    endpoints: list[Endpoint] = field(default_factory=list)


def _hp(url: str, defecto_puerto: int) -> tuple[str, int]:
    u = urlparse(url)
    return (u.hostname or ""), (u.port or defecto_puerto)


def construir(cfg: Config) -> dict[str, Dependencia]:
    deps: dict[str, Dependencia] = {}

    mh, mp = _hp(cfg["MONGODB_URI"] or "mongodb://localhost:27017", 27017)
    deps["mongodb"] = Dependencia(
        "mongodb", "Equipos y jugadores (documental)", "Hito 4",
        f"database {cfg['MONGODB_DATABASE']} / colecciones equipos, jugadores",
        "usuario y password en MONGODB_URI (authSource admin)",
        "pymongo (driver oficial)", "mongosh (dentro del contenedor)",
        cfg["MONGO_CONTAINER"], ["MONGODB_URI", "MONGODB_DATABASE"],
        ["MONGODB_URI", "MONGODB_DATABASE"],
        ["GET /equipos/{codigo}", "GET /equipos/{codigo}/jugadores"],
        [Endpoint("driver de la API", mh, mp, "MongoDB Wire Protocol (OP_MSG)", True)])

    nh, np_ = _hp(cfg["NEO4J_URI"], 7687)
    hh, hp = _hp(cfg["NEO4J_HTTP_URL"], 7474)
    deps["neo4j"] = Dependencia(
        "neo4j", "Partidos, eventos y participantes (grafo)", "Hito 5",
        f"database {cfg['NEO4J_DATABASE']}",
        f"usuario {cfg['NEO4J_USER']} + NEO4J_PASSWORD (basic auth sobre Bolt)",
        "neo4j (driver oficial, Bolt)", "cypher-shell (dentro del contenedor)",
        cfg["NEO4J_CONTAINER"], ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "NEO4J_DATABASE"],
        ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"],
        ["GET /partidos/{codigo}/eventos"],
        [Endpoint("driver de la API", nh, np_, "Bolt", True),
         Endpoint("Neo4j Browser / HTTP", hh, hp, "HTTP", False)])

    deps["cassandra"] = Dependencia(
        "cassandra", "Comentarios masivos (tabular)", "Hito 6",
        f"keyspace {cfg['CASSANDRA_KEYSPACE']} / tabla comentarios_por_partido",
        "sin autenticacion (AllowAllAuthenticator de la imagen de laboratorio)",
        "cassandra-driver; si no carga, cqlsh via docker exec", "cqlsh (dentro del contenedor)",
        cfg["CASSANDRA_CONTAINER"], ["CASSANDRA_HOST", "CASSANDRA_PORT", "CASSANDRA_KEYSPACE",
                                     "CASSANDRA_CONTAINER"],
        ["CASSANDRA_HOST", "CASSANDRA_PORT", "CASSANDRA_KEYSPACE"],
        ["GET /partidos/{codigo}/comentarios", "POST /partidos/{codigo}/comentarios"],
        [Endpoint("driver de la API", cfg["CASSANDRA_HOST"], int(cfg["CASSANDRA_PORT"]),
                  "CQL binary protocol (v4/v5)", True)])

    rh, rp = _hp(cfg["REDIS_URL"], 6379)
    deps["redis"] = Dependencia(
        "redis", "Sesiones y cache (clave/valor)", "Hito 7",
        f"base logica {urlparse(cfg['REDIS_URL']).path.strip('/') or '0'} / claves sesion:<id>",
        "sin password (requirepass vacio en el laboratorio)",
        "redis-py", "redis-cli (dentro del contenedor)",
        cfg["REDIS_CONTAINER"], ["REDIS_URL"], ["REDIS_URL"],
        ["GET /sesiones/{sesion_id}"],
        [Endpoint("driver de la API", rh, rp, "RESP", True)])

    ih, ip = _hp(cfg["INFLUX_URL"], 8181)
    deps["influxdb"] = Dependencia(
        "influxdb", "Estadisticas en vivo (series temporales)", "Hito 8",
        f"database {cfg['INFLUX_DATABASE']} / tabla estadisticas_equipo",
        "token Bearer (INFLUXDB3_TOKEN o INFLUXDB3_TOKEN_FILE)",
        "http.client (HTTP /api/v3/query_sql)", "influxdb3 CLI (dentro del contenedor)",
        cfg["INFLUX_CONTAINER"], ["INFLUX_URL", "INFLUX_DATABASE", "INFLUXDB3_TOKEN",
                                  "INFLUXDB3_TOKEN_FILE"],
        ["INFLUX_URL", "INFLUX_DATABASE", "INFLUXDB3_TOKEN"],
        ["GET /partidos/{codigo}/estadisticas"],
        [Endpoint("driver de la API", ih, ip, "HTTP (API v3)", True)])

    ph, pp = _hp(cfg["IRIS_PORTAL_URL"], 52773)
    deps["iris"] = Dependencia(
        "iris", "Entidades complejas: partido, eventos, designaciones (objetos)", "Hito 9",
        f"namespace {cfg['IRIS_NAMESPACE']} / esquema SQL Fixture",
        f"usuario {cfg['IRIS_USER']} + IRIS_PASSWORD",
        "intersystems-irispython (DB-API, Superserver)", "iris session (Terminal, dentro del contenedor)",
        cfg["IRIS_CONTAINER"], ["IRIS_HOST", "IRIS_PORT", "IRIS_NAMESPACE", "IRIS_USER",
                                "IRIS_PASSWORD"],
        ["IRIS_HOST", "IRIS_PORT", "IRIS_NAMESPACE", "IRIS_USER", "IRIS_PASSWORD"],
        ["GET /partidos/{codigo}/detalle"],
        [Endpoint("driver de la API (Superserver)", cfg["IRIS_HOST"], int(cfg["IRIS_PORT"]),
                  "IRIS Superserver (protocolo propio)", True),
         Endpoint("Management Portal", ph, pp, "HTTP", False)])
    return deps
