"""Registro (logging) con identificador de request para correlacion (RF18, RNF10).

Cada request entrante recibe un request_id corto. Ese id viaja por el contexto,
aparece en cada linea de log del adaptador y de la aplicacion, y se devuelve al
cliente (en el cuerpo de error y en el header X-Request-ID). Asi se puede
relacionar una respuesta con sus logs.

Los logs registran ruta, metodo, request_id, dependencia, resultado y duracion.
NUNCA registran secretos ni cuerpos sensibles (RNF7, RNF10): los adaptadores
loguean 'que paso', no el contenido.
"""
import contextvars
import logging
import sys
import uuid

# Variable de contexto: cada request la setea al entrar; los logs la leen.
_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def nuevo_request_id() -> str:
    return uuid.uuid4().hex[:8]


def set_request_id(valor: str) -> None:
    _request_id.set(valor)


def get_request_id() -> str:
    return _request_id.get()


class _FiltroRequestId(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def configurar_logging() -> logging.Logger:
    logger = logging.getLogger("fixture2030")
    if logger.handlers:  # ya configurado (evita duplicar en reloads)
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [req=%(request_id)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    handler.addFilter(_FiltroRequestId())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


logger = configurar_logging()
