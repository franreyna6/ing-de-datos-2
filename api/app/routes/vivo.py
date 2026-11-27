"""Rutas de la demo en vivo (Hito 13): un partido que atraviesa las seis bases.

Cada ruta dice en su descripcion que base decide y que base solo recibe la
propagacion. Solo opera sobre partidos de laboratorio (H13-DEMO-...).
"""
from fastapi import APIRouter, Body, Path, Query

from app.schemas.modelos import (ErrorResponse, EstadisticasEscritas, EventoVivoRegistrado,
                                  LoteEstadisticasVivo, NuevoEventoVivo, NuevoPartidoVivo,
                                  OperacionVivo, RelojVivo, TableroVivo)
from app.services import vivo

router = APIRouter(prefix="/vivo", tags=["demo en vivo (Hito 13)"])

_err = {400: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
        409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}
_codigo = Path(..., examples=["H13-DEMO-URUARG"])


@router.post("/partidos", response_model=OperacionVivo, status_code=201, responses=_err,
             summary="Crea un partido de laboratorio (IRIS decide; Neo4j y Redis reciben)",
             description="IRIS crea el objeto Partido en estado Programado y designa una terna "
                         "arbitral NEUTRAL (regla del Hito 9). Despues se crea el partido en el "
                         "grafo (DISPUTA, SE_JUEGA_EN) y la copia de estado en Redis.")
def post_partido(cuerpo: NuevoPartidoVivo = Body(...)):
    return vivo.crear_partido(cuerpo.codigo, cuerpo.local.upper(), cuerpo.visitante.upper(),
                              cuerpo.sede.upper(), cuerpo.fecha)


@router.post("/partidos/{codigo}/iniciar", response_model=OperacionVivo, responses=_err,
             summary="Programado -> EnJuego (IRIS valida la transicion)")
def post_iniciar(codigo: str = _codigo):
    return vivo.iniciar_partido(codigo)


@router.post("/partidos/{codigo}/eventos", response_model=EventoVivoRegistrado,
             status_code=201, responses=_err,
             summary="Registra un gol o una tarjeta (IRIS valida; Neo4j lo conecta)",
             description="IRIS aplica las reglas del partido: solo EnJuego, minuto 1-120 y "
                         "jugador de uno de los dos equipos. Si las viola: **409** con el "
                         "motivo que dio IRIS. Si se acepta, el evento se agrega a Neo4j como "
                         "nodo (evento -> jugador -> equipo) y el marcador se copia a Redis.")
def post_evento(codigo: str = _codigo, cuerpo: NuevoEventoVivo = Body(...)):
    return vivo.registrar_evento(codigo, cuerpo.tipo, cuerpo.minuto, cuerpo.jugadorCodigo)


@router.post("/partidos/{codigo}/finalizar", response_model=OperacionVivo, responses=_err,
             summary="EnJuego -> Finalizado (IRIS valida la transicion)")
def post_finalizar(codigo: str = _codigo):
    return vivo.finalizar_partido(codigo)


@router.put("/partidos/{codigo}/reloj", status_code=204, responses=_err,
            summary="Actualiza el minuto de juego (dato efimero: solo Redis)")
def put_reloj(codigo: str = _codigo, cuerpo: RelojVivo = Body(...)):
    vivo.actualizar_minuto(codigo, cuerpo.minuto)


@router.post("/partidos/{codigo}/estadisticas", response_model=EstadisticasEscritas,
             status_code=201, responses=_err,
             summary="Escribe estadisticas por segundo (InfluxDB, line protocol)",
             description="Mismo esquema del Hito 8: tags partido_id, equipo_id, sede, grupo; "
                         "fields posesion_pct, pases_acum, tiros_acum, recuperaciones_acum. "
                         "Lote maximo: 500 puntos.")
def post_estadisticas(codigo: str = _codigo, cuerpo: LoteEstadisticasVivo = Body(...)):
    return vivo.escribir_estadisticas(codigo, cuerpo.sede, cuerpo.grupo or "-",
                                      [p.model_dump() for p in cuerpo.puntos])


@router.get("/partidos/{codigo}/tablero", response_model=TableroVivo, responses=_err,
            summary="Una pantalla, seis bases (consultadas en paralelo)",
            description="Devuelve una seccion por base con su propio estado (ok, http, ms). "
                        "Si una base esta caida, SOLO su seccion trae error: el aislamiento "
                        "de fallas del Hito 10, visible en una sola respuesta.")
def get_tablero(codigo: str = Path(..., examples=["H13-DEMO-URUARG"]),
                local: str | None = Query(None, examples=["URU"]),
                visitante: str | None = Query(None, examples=["ARG"]),
                minutos: int = Query(10, ge=1, le=180,
                                     description="Ventana de estadisticas a agregar")):
    return vivo.tablero(codigo, local, visitante, minutos)
