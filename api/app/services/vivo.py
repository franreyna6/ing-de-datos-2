"""Casos de uso de la demo en vivo (Hito 13): un partido que atraviesa las seis bases.

Esta capa ORQUESTA; cada base hace solo lo que justifica su modelo:

  IRIS       fuente de verdad del partido como objeto con reglas: estado
             (Programado -> EnJuego -> Finalizado), terna, eventos y marcador.
             Decide si un gol o una tarjeta se acepta (409 si viola una regla).
  Neo4j      el evento aceptado se agrega como NODO conectado al partido y al
             jugador, para los recorridos (gol -> jugador -> equipo).
  MongoDB    fichas de los dos equipos y planteles (lectura).
  Cassandra  feed de comentarios del partido (escritura masiva, partition key
             (partido, ventana de 5 min)); la lectura pasa por la cache.
  Redis      sesiones con TTL deslizante, hinchas unicos (HyperLogLog), cache del
             feed y una copia rapida del estado del partido para el tablero.
  InfluxDB   estadisticas por segundo y su agregacion por ventanas (date_bin).

No hay transacciones entre motores (trade-off declarado desde el Hito 4). El
orden de escritura lo decide la fuente de verdad: primero IRIS valida y
persiste; despues se propaga a Neo4j y a Redis. Si una propagacion falla, la
respuesta lo dice en 'traza' (sincronizado=false): no se esconde.

Integridad (RNF5 del Hito 13): solo se escriben partidos de laboratorio con
codigo H13-DEMO-...; el fixture real no se modifica.
"""
from __future__ import annotations

import contextvars
import datetime as dt
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from app.adapters.influx_adapter import influx_adapter
from app.adapters.iris_adapter import iris_adapter
from app.adapters.mongo_adapter import mongo_adapter
from app.adapters.neo4j_adapter import neo4j_adapter
from app.adapters.redis_adapter import redis_adapter
from app.core.errores import (ErrorAPI, ErrorConflicto, ErrorNoEncontrado,
                              ErrorValidacion)
from app.services import servicios

PREFIJO = "H13-DEMO-"
_PATRON_LAB = re.compile(r"^H13-DEMO-[A-Z0-9-]{1,11}$")
_PATRON_EQUIPO = re.compile(r"^[A-Z]{3}$")

# TTL de la sesion del Hito 7: 30 min de INACTIVIDAD (se renueva con cada accion).
TTL_SESION_S = 1800

# Pool compartido para consultar las bases del tablero en paralelo.
_pool = ThreadPoolExecutor(max_workers=12, thread_name_prefix="tablero")


def _ahora() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def validar_codigo_lab(codigo: str) -> str:
    if not _PATRON_LAB.match(codigo or ""):
        raise ErrorValidacion(
            f"La demo solo escribe partidos de laboratorio con codigo {PREFIJO}XXXX "
            "(el fixture real no se modifica).", {"parametro": "codigo", "valor": codigo})
    return codigo


def _paso(traza: list, fuente: str, operacion: str, funcion, *args, critico=True, **kwargs):
    """Ejecuta un paso, mide su duracion y lo anota en la traza de la respuesta.

    critico=True: si falla, la excepcion sube (la operacion entera falla).
    critico=False: se anota sincronizado=false y se sigue (propagacion).
    """
    t0 = time.perf_counter()
    try:
        res = funcion(*args, **kwargs)
        traza.append({"fuente": fuente, "operacion": operacion, "ok": True,
                      "ms": round((time.perf_counter() - t0) * 1000, 1)})
        return res
    except ErrorAPI as e:
        traza.append({"fuente": fuente, "operacion": operacion, "ok": False,
                      "ms": round((time.perf_counter() - t0) * 1000, 1),
                      "error": e.code, "sincronizado": False})
        if critico:
            raise
        return None


def _iris(traza: list, metodo: str, *args) -> dict:
    """Llama a Fixture.Vivo; un rechazo de regla se convierte en 409 con el motivo."""
    r = _paso(traza, "iris", f"Fixture.Vivo.{metodo}", iris_adapter.vivo, metodo, *args)
    if not r.get("ok"):
        motivo = r.get("motivo") or "IRIS rechazo la operacion"
        if "No existe el partido" in motivo:
            raise ErrorNoEncontrado(motivo, {"code": "MATCH_NOT_FOUND", "fuente": "iris"})
        raise ErrorConflicto(f"IRIS rechazo la operacion: {motivo}",
                             {"code": "BUSINESS_RULE", "fuente": "iris", "motivo": motivo,
                              "traza": traza})
    return r


def _guardar_estado(traza: list, codigo: str, estado: dict) -> None:
    """Propaga la copia del estado a Redis. Si Redis cae, no frena la operacion."""
    t0 = time.perf_counter()
    ok = redis_adapter.vivo_guardar_estado(codigo, estado)
    paso = {"fuente": "redis", "operacion": "vivo_guardar_estado", "ok": ok,
            "ms": round((time.perf_counter() - t0) * 1000, 1)}
    if not ok:
        paso["sincronizado"] = False
    traza.append(paso)


def _estado_redis(r_iris: dict, extra: dict | None = None) -> dict:
    estado = {"estado": r_iris.get("estado"), "golesLocal": r_iris.get("golesLocal"),
              "golesVisitante": r_iris.get("golesVisitante"),
              "equipoLocal": r_iris.get("equipoLocal"),
              "equipoVisitante": r_iris.get("equipoVisitante"),
              "sede": r_iris.get("sede"), "actualizado": _ahora().isoformat()}
    if extra:
        estado.update(extra)
    return estado


# --------------------------------------------------------------------- escritura
def crear_partido(codigo: str | None, local: str, visitante: str, sede: str,
                  fecha: str) -> dict:
    for nombre, v in (("local", local), ("visitante", visitante)):
        if not _PATRON_EQUIPO.match(v or ""):
            raise ErrorValidacion(f"'{nombre}' debe ser un codigo FIFA de 3 letras.",
                                  {"parametro": nombre, "valor": v})
    if local == visitante:
        raise ErrorValidacion("Un equipo no puede jugar contra si mismo.")
    try:
        dt.date.fromisoformat(fecha)
    except ValueError:
        raise ErrorValidacion("'fecha' debe tener formato AAAA-MM-DD.", {"valor": fecha})
    codigo = validar_codigo_lab(codigo or f"{PREFIJO}{local}{visitante}")
    traza: list = []
    r = _iris(traza, "Crear", codigo, local, visitante, sede, fecha)
    grafo = _paso(traza, "neo4j", "crear_partido_lab", neo4j_adapter.crear_partido_lab,
                  codigo, fecha, "Centenario", local, visitante, sede, critico=False)
    _guardar_estado(traza, codigo, _estado_redis(r, {"minuto": 0, "inicio": ""}))
    return {"partido": r, "grafo": grafo, "traza": traza}


def iniciar_partido(codigo: str) -> dict:
    validar_codigo_lab(codigo)
    traza: list = []
    r = _iris(traza, "Iniciar", codigo)
    _guardar_estado(traza, codigo, _estado_redis(r, {"minuto": 0, "inicio": _ahora().isoformat()}))
    return {"partido": r, "traza": traza}


def registrar_evento(codigo: str, tipo: str, minuto: int, jugador: str) -> dict:
    validar_codigo_lab(codigo)
    if tipo not in ("Gol", "Tarjeta"):
        raise ErrorValidacion("'tipo' debe ser Gol o Tarjeta.", {"valor": tipo})
    evento = "EVD-" + uuid.uuid4().hex[:8].upper()
    traza: list = []
    # 1. IRIS decide (regla junto al dato) y persiste el evento y el marcador.
    r = _iris(traza, "RegistrarEvento", codigo, evento, tipo, int(minuto), jugador)
    # 2. Neo4j: el evento como nodo conectado (para los recorridos).
    grafo = _paso(traza, "neo4j", "registrar_evento", neo4j_adapter.registrar_evento,
                  codigo, evento, tipo, int(minuto), jugador,
                  r.get("golesLocal", 0), r.get("golesVisitante", 0), critico=False)
    # 3. Redis: copia rapida del marcador para el tablero.
    _guardar_estado(traza, codigo, _estado_redis(r, {"minuto": minuto, "ultimoEvento": f"{tipo} {minuto}'"}))
    return {"evento": evento, "tipo": tipo, "minuto": minuto, "jugador": jugador,
            "partido": r, "grafo": grafo, "traza": traza}


def finalizar_partido(codigo: str) -> dict:
    validar_codigo_lab(codigo)
    traza: list = []
    r = _iris(traza, "Finalizar", codigo)
    _guardar_estado(traza, codigo, _estado_redis(r, {"minuto": 90}))
    return {"partido": r, "traza": traza}


def actualizar_minuto(codigo: str, minuto: int) -> None:
    """El reloj del partido es efimero: vive solo en Redis (lo escribe el simulador)."""
    validar_codigo_lab(codigo)
    redis_adapter.vivo_guardar_estado(codigo, {"minuto": minuto,
                                               "actualizado": _ahora().isoformat()})


def escribir_estadisticas(codigo: str, sede: str, grupo: str, puntos: list[dict]) -> dict:
    validar_codigo_lab(codigo)
    if not puntos:
        raise ErrorValidacion("'puntos' no puede estar vacio.")
    if len(puntos) > 500:
        raise ErrorValidacion("Maximo 500 puntos por escritura (lote acotado, RNF12).")
    ahora = int(_ahora().timestamp())
    for p in puntos:
        if not (0 <= float(p["posesionPct"]) <= 100):
            raise ErrorValidacion("posesionPct debe estar entre 0 y 100.")
        p.setdefault("ts", ahora)
        if p["ts"] is None:
            p["ts"] = ahora
    n = influx_adapter.escribir_estadisticas(codigo, sede, grupo, puntos)
    return {"partido": codigo, "puntosEscritos": n}


# ---------------------------------------------------------------------- sesiones
def crear_sesion(usuario_id: str, rol: str, partido: str | None) -> dict:
    sesion_id = "s-" + uuid.uuid4().hex[:12]
    return redis_adapter.crear_sesion(sesion_id, usuario_id, rol, TTL_SESION_S, partido)


def renovar_sesion(sesion_id: str) -> dict:
    datos = redis_adapter.renovar_sesion(sesion_id, TTL_SESION_S)
    if datos is None:
        raise ErrorNoEncontrado("La sesion ya vencio: hay que volver a autenticarse.",
                                {"code": "SESSION_EXPIRED_OR_NOT_FOUND", "recurso": sesion_id})
    return datos


# ---------------------------------------------------------------------- tablero
def _seccion(fuente: str, funcion, *args) -> dict:
    t0 = time.perf_counter()
    try:
        datos = funcion(*args)
        return {"fuente": fuente, "ok": True, "http": 200,
                "ms": round((time.perf_counter() - t0) * 1000, 1), "datos": datos}
    except ErrorAPI as e:
        return {"fuente": fuente, "ok": False, "http": e.http,
                "ms": round((time.perf_counter() - t0) * 1000, 1),
                "error": {"code": e.code, "message": e.mensaje}}
    except Exception:
        return {"fuente": fuente, "ok": False, "http": 500,
                "ms": round((time.perf_counter() - t0) * 1000, 1),
                "error": {"code": "INTERNAL_ERROR", "message": "Error inesperado"}}


def _en_paralelo(tareas: dict) -> dict:
    """Corre cada seccion en un hilo, con el request-id del request (logs)."""
    futuros = {nombre: _pool.submit(contextvars.copy_context().run, _seccion, *tarea)
               for nombre, tarea in tareas.items()}
    return {nombre: f.result() for nombre, f in futuros.items()}


def _estado_iris(codigo: str) -> dict:
    r = iris_adapter.vivo("Estado", codigo)
    if not r.get("ok"):
        raise ErrorNoEncontrado(r.get("motivo") or f"No existe el partido '{codigo}'.")
    return r


def _comentarios(codigo: str) -> dict:
    pagina, cache = servicios.comentarios_de_partido_con_cache(codigo, None, 15)
    return {**pagina, "cache": cache}


def _serie(codigo: str, minutos: int) -> dict:
    hasta = _ahora() + dt.timedelta(seconds=5)
    desde = hasta - dt.timedelta(minutes=minutos)
    puntos = influx_adapter.serie_agregada(codigo, desde.isoformat().replace("+00:00", "Z"),
                                           hasta.isoformat().replace("+00:00", "Z"), 10)
    return {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "pasoSegundos": 10,
            "puntos": puntos}


def _fichas(local: str, visitante: str) -> dict:
    return {"local": servicios.obtener_equipo(local),
            "visitante": servicios.obtener_equipo(visitante)}


def tablero(codigo: str, local: str | None, visitante: str | None,
            minutos: int = 10) -> dict:
    """Una pantalla, seis bases, consultadas EN PARALELO.

    Cada seccion trae su propio estado (ok, http, ms): si una base cae, solo su
    seccion viene con error y el resto se muestra. Es el aislamiento de fallas
    del Hito 10 visible en una sola respuesta.
    """
    t0 = time.perf_counter()
    secciones = _en_paralelo({
        "partido": ("iris", _estado_iris, codigo),
        "eventos": ("neo4j", servicios.eventos_de_partido, codigo, 50),
        "comentarios": ("cassandra", _comentarios, codigo),
        "vivo": ("redis", redis_adapter.vivo_leer, codigo),
        "estadisticas": ("influxdb", _serie, codigo, minutos),
    })
    # Los equipos se toman del pedido, o de IRIS, o de la copia en Redis.
    if not (local and visitante):
        for fuente in ("partido", "vivo"):
            s = secciones[fuente]
            if s["ok"]:
                datos = s["datos"] if fuente == "partido" else s["datos"].get("estado", {})
                local = local or datos.get("equipoLocal")
                visitante = visitante or datos.get("equipoVisitante")
    if local and visitante:
        secciones["equipos"] = _seccion("mongodb", _fichas, local, visitante)
    else:
        secciones["equipos"] = {"fuente": "mongodb", "ok": False, "http": 400, "ms": 0,
                                "error": {"code": "VALIDATION_ERROR",
                                          "message": "No se conocen los equipos del partido."}}
    return {"partido": codigo, "generado": _ahora().isoformat(),
            "msTotal": round((time.perf_counter() - t0) * 1000, 1),
            "secciones": secciones}
