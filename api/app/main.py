"""Aplicacion FastAPI: ensambla rutas, salud, request-id y manejo de errores.

Responsabilidades de este archivo (y solo estas):
  - crear la app y montar los routers por recurso;
  - asignar un request-id a cada request y devolverlo en X-Request-ID (RF18);
  - traducir las excepciones de dominio (core.errores) al HTTP correspondiente,
    con el formato de error comun (RF11, RF12, RNF4). Los adaptadores lanzan
    'que paso'; aca se decide el codigo HTTP. Asi ninguna capa de datos conoce HTTP.

FastAPI genera el OpenAPI y Swagger UI a partir de las rutas y schemas (RF13):
  - Swagger UI: http://localhost:8000/docs
  - OpenAPI JSON: http://localhost:8000/openapi.json
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.routing import Match

from app.core import metricas
from app.core.errores import ErrorAPI, ErrorValidacion, cuerpo_error
from app.core.registro import logger, nuevo_request_id, set_request_id, get_request_id
from app.routes import equipos, partidos, sesiones
from app.schemas.modelos import Salud
from app.services import servicios
from app.adapters.cassandra_adapter import cassandra_adapter
from app.adapters.influx_adapter import influx_adapter
from app.adapters.iris_adapter import iris_adapter
from app.adapters.mongo_adapter import mongo_adapter
from app.adapters.neo4j_adapter import neo4j_adapter
from app.adapters.redis_adapter import redis_adapter

# --- Hito 13: medicion de cada llamada a una base (RF4) y corte rapido ---
# Se envuelven los metodos publicos de cada adaptador. Ver app/core/metricas.py
# y app/core/cortocircuito.py (mejora transversal sacada de la evidencia).
metricas.instrumentar_adaptador(mongo_adapter, "mongodb", ["obtener_equipo", "listar_jugadores"])
metricas.instrumentar_adaptador(neo4j_adapter, "neo4j", ["eventos_de_partido"])
metricas.instrumentar_adaptador(cassandra_adapter, "cassandra",
                                ["leer_comentarios", "escribir_comentario"])
metricas.instrumentar_adaptador(redis_adapter, "redis",
                                ["obtener_sesion", "cache_leer", "cache_guardar"],
                                sin_corte=("cache_leer", "cache_guardar"))
metricas.instrumentar_adaptador(influx_adapter, "influxdb", ["estadisticas"])
metricas.instrumentar_adaptador(iris_adapter, "iris", ["detalle_partido"])

_CHEQUEOS = {
    "mongodb": mongo_adapter.verificar,
    "neo4j": neo4j_adapter.verificar,
    "cassandra": cassandra_adapter.verificar,
    "redis": redis_adapter.verificar,
    "influxdb": influx_adapter.verificar,
    "iris": iris_adapter.verificar,
}


@asynccontextmanager
async def ciclo_de_vida(app_: FastAPI):
    # Hito 13: disponibilidad de cada fuente en segundo plano para /metrics.
    metricas.iniciar_chequeo_de_dependencias(_CHEQUEOS)
    yield


app = FastAPI(
    title="Fixture 2030 API integrada",
    version="1.0.0",
    description="API REST que expone casos de uso del Fixture Mundial 2030 sobre "
                "seis fuentes NoSQL (MongoDB, Neo4j, Cassandra, Redis, InfluxDB e "
                "IRIS) mediante adaptadores separados. Hito 10 - Grupo 8.",
    lifespan=ciclo_de_vida,
)

app.include_router(equipos.router)
app.include_router(partidos.router)
app.include_router(sesiones.router)


def _plantilla_de_ruta(request: Request) -> str:
    """Plantilla de la ruta atendida (/partidos/{codigo}/eventos), no la URL real.

    Asi la etiqueta 'ruta' de las metricas tiene pocos valores posibles aunque
    lleguen miles de codigos distintos (control de cardinalidad, Hito 13).
    """
    for ruta in request.app.router.routes:
        coincide, _ = ruta.matches(request.scope)
        if coincide == Match.FULL:
            return getattr(ruta, "path", "sin_ruta")
    return "sin_ruta"


# --- Request-id: correlacion respuesta <-> logs (RF18, RNF10) ---
@app.middleware("http")
async def middleware_request_id(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or nuevo_request_id()
    set_request_id(rid)
    import time
    t0 = time.perf_counter()
    try:
        respuesta = await call_next(request)
    except Exception:
        # Error no previsto: lo responde el manejador de Exception (500). Se
        # cuenta igual para que la tasa de errores no lo pierda (Hito 13).
        if request.url.path != "/metrics":
            ruta = _plantilla_de_ruta(request)
            metricas.REQUESTS.labels(request.method, ruta, "500").inc()
            metricas.DURACION.labels(request.method, ruta).observe(time.perf_counter() - t0)
        raise
    dur_ms = (time.perf_counter() - t0) * 1000
    respuesta.headers["X-Request-ID"] = rid
    # Hito 12: tiempo medido DENTRO de la API. El generador de carga lo compara
    # con su propia latencia para separar tiempo de API vs. red/cola/cliente.
    respuesta.headers["X-Duracion-ms"] = f"{dur_ms:.2f}"
    # Hito 13: la misma duracion alimenta las metricas de Prometheus (RF4).
    # /metrics no se mide a si misma para no mezclar el scrape con el trafico real.
    if request.url.path != "/metrics":
        ruta = _plantilla_de_ruta(request)
        metricas.REQUESTS.labels(request.method, ruta, str(respuesta.status_code)).inc()
        metricas.DURACION.labels(request.method, ruta).observe(dur_ms / 1000)
    logger.info("%s %s -> %s (%.1f ms)",
                request.method, request.url.path, respuesta.status_code, dur_ms)
    return respuesta


# --- Manejo central de errores (RF11, RF12, RNF4, RNF9) ---
@app.exception_handler(ErrorAPI)
async def manejar_error_api(request: Request, exc: ErrorAPI):
    # La causa tecnica (si existe) va SOLO al log, nunca al cliente (RF12, RNF7).
    causa = getattr(exc, "causa", None)
    if causa:
        logger.warning("dependencia fuente=%s causa=%s", exc.detalles.get("fuente"), causa)
    return JSONResponse(
        status_code=exc.http,
        content=cuerpo_error(exc.code, exc.mensaje, get_request_id(), exc.detalles),
    )


@app.exception_handler(RequestValidationError)
async def manejar_validacion(request: Request, exc: RequestValidationError):
    # Error de validacion de FastAPI/Pydantic -> formato comun 400 (RNF3, RNF4).
    campos = [{"campo": ".".join(str(x) for x in e.get("loc", [])), "motivo": e.get("msg")}
              for e in exc.errors()]
    return JSONResponse(
        status_code=400,
        content=cuerpo_error(ErrorValidacion.code,
                             "Parametros o cuerpo invalidos.",
                             get_request_id(), {"campos": campos}),
    )


@app.exception_handler(Exception)
async def manejar_inesperado(request: Request, exc: Exception):
    # Error no previsto: 500 seguro. El detalle tecnico queda en el log (RF12).
    logger.error("error inesperado en %s: %s", request.url.path, repr(exc))
    return JSONResponse(
        status_code=500,
        content=cuerpo_error("INTERNAL_ERROR",
                             "Ocurrio un error interno al procesar la solicitud.",
                             get_request_id()),
    )


# --- Salud / conectividad (RF17, RNF11) ---
@app.get("/salud", response_model=Salud, tags=["sistema"],
         summary="Estado de la API y disponibilidad de cada fuente")
def salud():
    return {"api": "ok", "dependencias": servicios.verificar_dependencias()}


# --- Metricas para Prometheus (Hito 13, RF4) ---
@app.get("/metrics", include_in_schema=False)
def metrics():
    """Formato de texto de Prometheus. Solo lectura: no consulta ninguna base."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
