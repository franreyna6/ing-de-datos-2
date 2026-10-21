"""Servicios / casos de uso (RF9, RNF1).

Capa intermedia entre las rutas (HTTP) y los adaptadores (drivers). Aplica las
reglas del caso de uso y la validacion de negocio que no cubre el schema, y
traduce 'no encontrado' (None del adaptador) en la excepcion de dominio
correspondiente. No conoce HTTP ni drivers: recibe datos validados y devuelve
datos, o lanza una excepcion de core.errores.

Mantener esto separado es lo que pide RNF1: las rutas no mezclan HTTP, reglas y
acceso a datos en un solo bloque.
"""
from __future__ import annotations

import datetime as dt

from app.adapters.cassandra_adapter import cassandra_adapter
from app.adapters.influx_adapter import influx_adapter
from app.adapters.iris_adapter import iris_adapter
from app.adapters.mongo_adapter import mongo_adapter
from app.adapters.neo4j_adapter import neo4j_adapter
from app.adapters.redis_adapter import redis_adapter
from app.core.config import obtener_config
from app.core.errores import ErrorNoEncontrado, ErrorValidacion

_cfg = obtener_config()


def _acotar_limit(limit: int) -> int:
    """Aplica el tope global de la API (RNF12): aunque pidan mas, se recorta."""
    if limit < 1:
        raise ErrorValidacion("El parametro 'limit' debe ser mayor o igual a 1.")
    return min(limit, _cfg.max_limit)


def _parse_instante(valor: str, nombre: str) -> dt.datetime:
    """Valida y parsea un instante ISO-8601 (RNF3). Acepta sufijo 'Z'."""
    try:
        return dt.datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise ErrorValidacion(
            f"El parametro '{nombre}' no es una fecha-hora ISO-8601 valida.",
            {"parametro": nombre, "valor": valor})


# --- MongoDB ---
def obtener_equipo(codigo: str) -> dict:
    doc = mongo_adapter.obtener_equipo(codigo)
    if doc is None:
        raise ErrorNoEncontrado(f"No existe el equipo '{codigo}'.",
                                {"code": "TEAM_NOT_FOUND", "recurso": codigo})
    return doc


def listar_jugadores(equipo_codigo: str, posicion: str | None,
                     limit: int, offset: int) -> dict:
    limit = _acotar_limit(limit)
    if offset < 0:
        raise ErrorValidacion("El parametro 'offset' no puede ser negativo.")
    filas = mongo_adapter.listar_jugadores(equipo_codigo, posicion, limit, offset)
    return {"equipoCodigo": equipo_codigo, "total": len(filas), "jugadores": filas}


# --- Neo4j ---
def eventos_de_partido(codigo: str, limit: int) -> dict:
    limit = _acotar_limit(limit)
    res = neo4j_adapter.eventos_de_partido(codigo, limit)
    if res is None:
        raise ErrorNoEncontrado(f"No existe el partido '{codigo}'.",
                                {"code": "MATCH_NOT_FOUND", "recurso": codigo})
    return res


# --- Cassandra ---
def comentarios_de_partido(partido: str, instante_iso: str | None, limit: int) -> dict:
    limit = _acotar_limit(limit)
    instante = (_parse_instante(instante_iso, "instante")
                if instante_iso else dt.datetime.now(dt.timezone.utc))
    return cassandra_adapter.leer_comentarios(partido, instante, limit)


def crear_comentario(partido: str, usuario_id: str, contenido: str,
                     comentario_id: str | None) -> dict:
    return cassandra_adapter.escribir_comentario(partido, usuario_id, contenido, comentario_id)


# --- Redis ---
def obtener_sesion(sesion_id: str) -> dict:
    datos = redis_adapter.obtener_sesion(sesion_id)
    if datos is None:
        # Clave ausente o expirada: 404, no 503 (la base SI respondio).
        raise ErrorNoEncontrado(
            "No existe una sesion vigente con ese identificador.",
            {"code": "SESSION_EXPIRED_OR_NOT_FOUND", "recurso": sesion_id})
    return datos


# --- InfluxDB ---
def estadisticas_de_partido(partido: str, desde: str, hasta: str) -> dict:
    d = _parse_instante(desde, "desde")
    h = _parse_instante(hasta, "hasta")
    if d >= h:
        raise ErrorValidacion("El parametro 'desde' debe ser anterior a 'hasta'.")
    # Duracion maxima de la ventana para no traer un volumen ilimitado (RNF12).
    if (h - d) > dt.timedelta(hours=3):
        raise ErrorValidacion("La ventana temporal no puede superar las 3 horas.")
    return influx_adapter.estadisticas(partido, desde, hasta)


# --- IRIS ---
def detalle_de_partido(codigo: str) -> dict:
    res = iris_adapter.detalle_partido(codigo)
    if res is None:
        raise ErrorNoEncontrado(f"No existe el partido '{codigo}'.",
                                {"code": "MATCH_NOT_FOUND", "recurso": codigo})
    return res


# --- Salud ---
def verificar_dependencias() -> list[dict]:
    """Chequea cada fuente sin lanzar; alimenta /salud (RF17, RNF11)."""
    return [
        {"fuente": "mongodb", "disponible": mongo_adapter.verificar()},
        {"fuente": "neo4j", "disponible": neo4j_adapter.verificar()},
        {"fuente": "cassandra", "disponible": cassandra_adapter.verificar()},
        {"fuente": "redis", "disponible": redis_adapter.verificar()},
        {"fuente": "influxdb", "disponible": influx_adapter.verificar()},
        {"fuente": "iris", "disponible": iris_adapter.verificar()},
    ]
