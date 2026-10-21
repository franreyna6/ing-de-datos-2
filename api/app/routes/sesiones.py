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
