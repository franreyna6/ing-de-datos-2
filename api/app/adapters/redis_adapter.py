"""Adaptador clave/valor: Redis (Hito 7) — sesiones y estado temporal.

Unico lugar que conoce el cliente de Redis (RNF5). La distincion central de la
clase: una clave AUSENTE (expiro por TTL o nunca existio) NO es lo mismo que
Redis NO DISPONIBLE. La primera es un 404 de la aplicacion; la segunda, un 503.
Este adaptador las separa con dos caminos distintos, y nunca convierte una caida
en un 200 vacio.

Convencion de claves del Hito 7: 'sesion:<id>'. Solo se exponen los campos que
el consumidor necesita, no el valor interno completo.
"""
from __future__ import annotations

import json

from app.core.config import obtener_config
from app.core.errores import ErrorDependencia
from app.core.registro import logger

FUENTE = "redis"


class RedisAdapter:
    def __init__(self) -> None:
        self._cfg = obtener_config()
        self._client = None

    def _cli(self):
        if self._client is None:
            import redis
            self._client = redis.from_url(
                self._cfg.redis_url,
                socket_connect_timeout=self._cfg.dep_timeout_s,
                socket_timeout=self._cfg.dep_timeout_s,
                decode_responses=True,
            )
        return self._client

    def verificar(self) -> bool:
        try:
            return bool(self._cli().ping())
        except Exception:
            return False

    def obtener_sesion(self, sesion_id: str) -> dict | None:
        """Devuelve el estado de sesion, o None si la clave no existe/expiro.

        Lanza ErrorDependencia SOLO si Redis no responde (no por clave ausente).
        """
        clave = f"sesion:{sesion_id}"
        try:
            valor = self._cli().get(clave)
            ttl = self._cli().ttl(clave) if valor is not None else -2
        except Exception as e:
            # Error de conexion/timeout -> dependencia caida (503), NO 404.
            logger.warning("redis error sesion=%s", sesion_id)
            raise ErrorDependencia(FUENTE, str(e))

        if valor is None:
            logger.info("redis sesion=%s ausente_o_expirada", sesion_id)
            return None  # el servicio lo traduce a 404

        try:
            datos = json.loads(valor)
        except (ValueError, TypeError):
            datos = {"raw": valor}
        logger.info("redis sesion=%s activa ttl=%s", sesion_id, ttl)
        # Solo los campos utiles para el consumidor (no el valor interno entero).
        return {
            "sesionId": sesion_id,
            "usuarioId": datos.get("usuario_id") or datos.get("usuarioId"),
            "estado": "activa",
            "ttlSegundos": ttl if ttl is not None and ttl >= 0 else None,
        }

    def cerrar(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None


redis_adapter = RedisAdapter()
