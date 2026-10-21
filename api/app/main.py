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

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errores import ErrorAPI, ErrorValidacion, cuerpo_error
from app.core.registro import logger, nuevo_request_id, set_request_id, get_request_id
from app.routes import equipos, partidos, sesiones
from app.schemas.modelos import Salud
from app.services import servicios

app = FastAPI(
    title="Fixture 2030 API integrada",
    version="1.0.0",
    description="API REST que expone casos de uso del Fixture Mundial 2030 sobre "
                "seis fuentes NoSQL (MongoDB, Neo4j, Cassandra, Redis, InfluxDB e "
                "IRIS) mediante adaptadores separados. Hito 10 - Grupo 8.",
)

app.include_router(equipos.router)
app.include_router(partidos.router)
app.include_router(sesiones.router)


# --- Request-id: correlacion respuesta <-> logs (RF18, RNF10) ---
@app.middleware("http")
async def middleware_request_id(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or nuevo_request_id()
    set_request_id(rid)
    import time
    t0 = time.perf_counter()
    respuesta = await call_next(request)
    dur_ms = (time.perf_counter() - t0) * 1000
    respuesta.headers["X-Request-ID"] = rid
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
