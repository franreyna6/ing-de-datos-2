"""Rutas de equipos y jugadores -> MongoDB (RF3).

Caso de uso: la aplicacion muestra la ficha de un equipo y su plantel. La ruta
solo valida (via tipos y Query), delega en el servicio y describe el contrato
para OpenAPI. No conoce el driver de Mongo.
"""
from fastapi import APIRouter, Query, Path

from app.schemas.modelos import Equipo, ListaJugadores, ErrorResponse
from app.services import servicios

router = APIRouter(tags=["equipos"])

_err = {404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


@router.get("/equipos/{codigo}", response_model=Equipo,
            summary="Recupera un equipo desde el modulo documental (MongoDB)",
            responses=_err)
def get_equipo(codigo: str = Path(..., examples=["ARG"])):
    return servicios.obtener_equipo(codigo)


@router.get("/equipos/{codigo}/jugadores", response_model=ListaJugadores,
            summary="Lista paginada de jugadores de un equipo (MongoDB)",
            responses={503: {"model": ErrorResponse}})
def get_jugadores(
    codigo: str = Path(..., examples=["ARG"]),
    posicion: str | None = Query(None, examples=["Delantero"]),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return servicios.listar_jugadores(codigo, posicion, limit, offset)
