"""Rutas del recurso 'partido' -> Neo4j, Cassandra, InfluxDB e IRIS.

Un partido es un recurso del Fixture que distintas fuentes describen desde su
modelo: sus eventos (grafo), sus comentarios (tabular por particion), sus
estadisticas (serie temporal) y su detalle como entidad compleja (objetos). Cada
sub-ruta deja claro que fuente la atiende; ninguna mezcla modelos.
"""
from fastapi import APIRouter, Query, Path, Body, Response

from app.schemas.modelos import (EventosDePartido, PaginaComentarios, NuevoComentario,
                                  ComentarioCreado, Estadisticas, DetallePartido,
                                  ErrorResponse)
from app.services import servicios

router = APIRouter(tags=["partidos"])
_err = {404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


# --- Neo4j: eventos conectados al partido (RF4) ---
@router.get("/partidos/{codigo}/eventos", response_model=EventosDePartido,
            summary="Eventos conectados a un partido (Neo4j)", responses=_err)
def get_eventos(codigo: str = Path(..., examples=["F2030-001"]),
                limit: int = Query(50, ge=1, le=100)):
    return servicios.eventos_de_partido(codigo, limit)


# --- Cassandra: comentarios de una particion (RF5) ---
@router.get("/partidos/{codigo}/comentarios", response_model=PaginaComentarios,
            summary="Comentarios de un partido en una ventana de 5 min (Cassandra)",
            responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
def get_comentarios(
    response: Response,
    codigo: str = Path(..., examples=["F2030-063"]),
    instante: str | None = Query(
        None, description="Instante ISO-8601 dentro de la ventana a leer. "
                          "Si se omite, se usa la hora actual.",
        examples=["2030-06-22T20:23:00Z"]),
    limit: int = Query(20, ge=1, le=100),
):
    # Hito 12: el header X-Cache (OFF | MISS | HIT) permite medir la tasa de
    # aciertos desde el generador de carga sin cambiar el cuerpo del contrato.
    pagina, estado_cache = servicios.comentarios_de_partido_con_cache(codigo, instante, limit)
    response.headers["X-Cache"] = estado_cache
    return pagina


@router.post("/partidos/{codigo}/comentarios", response_model=ComentarioCreado,
             status_code=201,
             summary="Publica un comentario en un partido (Cassandra)",
             responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
def post_comentario(codigo: str = Path(..., examples=["F2030-063"]),
                    cuerpo: NuevoComentario = Body(...)):
    return servicios.crear_comentario(codigo, cuerpo.usuarioId, cuerpo.contenido,
                                      cuerpo.comentarioId)


# --- InfluxDB: estadisticas en una ventana temporal (RF7) ---
@router.get("/partidos/{codigo}/estadisticas", response_model=Estadisticas,
            summary="Estadisticas temporales de un partido en un intervalo (InfluxDB)",
            responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
def get_estadisticas(
    codigo: str = Path(..., examples=["F2030-018"]),
    desde: str = Query(..., examples=["2030-06-13T09:00:00Z"]),
    hasta: str = Query(..., examples=["2030-06-13T09:15:00Z"]),
):
    return servicios.estadisticas_de_partido(codigo, desde, hasta)


# --- IRIS: detalle de la entidad compleja (RF8) ---
@router.get("/partidos/{codigo}/detalle", response_model=DetallePartido,
            summary="Detalle del partido como entidad compleja (IRIS)", responses=_err)
def get_detalle(codigo: str = Path(..., examples=["F2030-001"])):
    return servicios.detalle_de_partido(codigo)
