"""Ruta de sesiones -> Redis (RF6).

Caso de uso: verificar si una sesion esta vigente. El contrato distingue sesion
activa (200), sesion ausente o expirada (404) y Redis no disponible (503). Esa
diferencia la resuelve el servicio/adaptador; la ruta solo la expone.
"""
from fastapi import APIRouter, Path

from app.schemas.modelos import Sesion, ErrorResponse
from app.services import servicios

router = APIRouter(tags=["sesiones"])


@router.get("/sesiones/{sesion_id}", response_model=Sesion,
            summary="Estado de una sesion de usuario (Redis)",
            responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
def get_sesion(sesion_id: str = Path(..., examples=["s-demo-001"])):
    return servicios.obtener_sesion(sesion_id)


# --- Hito 13: demo en vivo -------------------------------------------------
# El ciclo de vida completo de la sesion del Hito 7 expuesto en la API: crear
# (HSET + EXPIRE en MULTI/EXEC) y renovar con TTL DESLIZANTE (cada accion vuelve
# a poner los 30 minutos). Una sesion vencida no se resucita: 404 y reautenticar.
from fastapi import Body  # noqa: E402

from app.schemas.modelos import NuevaSesion, SesionActiva  # noqa: E402
from app.services import vivo  # noqa: E402


@router.post("/sesiones", response_model=Sesion, status_code=201,
             summary="Crea una sesion (Redis Hash con TTL de 30 min de inactividad)",
             responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
def post_sesion(cuerpo: NuevaSesion = Body(...)):
    return vivo.crear_sesion(cuerpo.usuarioId, cuerpo.rol, cuerpo.partido)


@router.post("/sesiones/{sesion_id}/actividad", response_model=SesionActiva,
             summary="Registra actividad y renueva el TTL (TTL deslizante, Redis)",
             responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
def post_actividad(sesion_id: str = Path(..., examples=["s-1a2b3c4d5e6f"])):
    return vivo.renovar_sesion(sesion_id)
