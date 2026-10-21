"""Formato de error comun y excepciones de dominio (RF11, RF12, RNF4).

Toda respuesta de error de la API tiene la misma forma, para que el consumidor
identifique el tipo de problema sin recibir stack traces, consultas internas ni
credenciales (RF12):

    {
      "error": {
        "code": "TEAM_NOT_FOUND",      # codigo estable de dominio
        "message": "No existe el equipo solicitado",
        "request_id": "a1b2c3d4"       # correlacion con los logs (RF18)
      }
    }

Las clases de abajo son las unicas que los servicios/adaptadores lanzan. El
manejador central (main.py) las traduce al HTTP correspondiente. Asi la capa de
acceso nunca decide codigos HTTP: solo describe QUE paso.
"""
from __future__ import annotations


class ErrorAPI(Exception):
    """Error con traduccion HTTP conocida. http y code son estables y publicos."""

    http: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, mensaje: str, detalles: dict | None = None) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalles = detalles or {}


class ErrorValidacion(ErrorAPI):
    """Parametro o cuerpo invalido. Se detecta ANTES de consultar la base (RNF3)."""

    http = 400
    code = "VALIDATION_ERROR"


class ErrorNoEncontrado(ErrorAPI):
    """El recurso pedido no existe. Distinto de 'dependencia caida' (RF11)."""

    http = 404
    code = "NOT_FOUND"


class ErrorConflicto(ErrorAPI):
    """El estado actual del recurso no permite la operacion (RF11, 409)."""

    http = 409
    code = "CONFLICT"


class ErrorDependencia(ErrorAPI):
    """Una fuente (base) esta caida, no responde o excede el timeout (RF11, RNF9).

    Nunca lleva el detalle tecnico al cliente: el mensaje interno va al log y al
    consumidor solo se le dice que la dependencia no esta disponible.
    """

    http = 503
    code = "DEPENDENCY_UNAVAILABLE"

    def __init__(self, fuente: str, causa: str | None = None) -> None:
        super().__init__(
            f"La fuente '{fuente}' no esta disponible en este momento.",
            detalles={"fuente": fuente},
        )
        # causa queda SOLO para el log; no se serializa al cliente.
        self.causa = causa


def cuerpo_error(code: str, message: str, request_id: str,
                 detalles: dict | None = None) -> dict:
    """Arma el JSON de error con la forma unica de la API (RNF4)."""
    error = {"code": code, "message": message, "request_id": request_id}
    if detalles:
        error["detalles"] = detalles
    return {"error": error}
