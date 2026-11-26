"""Adaptador clave/valor: Redis (Hito 7) — sesiones y estado temporal.

Unico lugar que conoce el cliente de Redis (RNF5). La distincion central de la
clase: una clave AUSENTE (expiro por TTL o nunca existio) NO es lo mismo que
Redis NO DISPONIBLE. La primera es un 404 de la aplicacion; la segunda, un 503.
Este adaptador las separa con dos caminos distintos, y nunca convierte una caida
en un 200 vacio.

Convencion de claves del Hito 7: 'sesion:<id>' es un HASH con los campos
usuario_id, rol, estado, creada_en, ultimo_acceso y acciones. Se lee con HGETALL
y solo se exponen los campos que el consumidor necesita, no el hash completo. Un
HGETALL vacio significa clave ausente o expirada (404), no Redis caido (503).
"""
from __future__ import annotations

import json

from app.core import cortocircuito
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
            # La sesion del Hito 7 es un HASH: HGETALL devuelve {} si no existe.
            datos = self._cli().hgetall(clave)
            ttl = self._cli().ttl(clave) if datos else -2
        except Exception as e:
            # Error de conexion/timeout -> dependencia caida (503), NO 404.
            logger.warning("redis error sesion=%s", sesion_id)
            raise ErrorDependencia(FUENTE, str(e))

        if not datos:
            logger.info("redis sesion=%s ausente_o_expirada", sesion_id)
            return None  # el servicio lo traduce a 404

        logger.info("redis sesion=%s estado=%s ttl=%s", sesion_id,
                    datos.get("estado"), ttl)
        # Solo los campos utiles para el consumidor (no el hash interno entero).
        return {
            "sesionId": sesion_id,
            "usuarioId": datos.get("usuario_id") or datos.get("usuarioId"),
            "estado": datos.get("estado", "activa"),
            "ttlSegundos": ttl if ttl is not None and ttl >= 0 else None,
        }

    # ------------------------------------------------ Hito 12: cache de lectura
    # A diferencia de las sesiones (donde Redis ES la fuente de verdad y una
    # caida es 503), aca Redis es solo una cache: si no responde, se devuelve
    # None y el servicio lee Cassandra. Una falla de la cache nunca rompe la
    # lectura de comentarios; solo la vuelve mas lenta.
    def cache_leer(self, clave: str) -> dict | None:
        # Hito 13: con el corte abierto (Redis fallo hace poco) no se intenta:
        # se devuelve None al instante y el servicio lee Cassandra.
        corte = cortocircuito.de(FUENTE)
        if not corte.permitir():
            return None
        try:
            valor = self._cli().get(clave)
        except Exception:
            corte.registrar_falla()
            logger.warning("redis cache no disponible (lectura) clave=%s", clave)
            return None
        corte.registrar_exito()
        if valor is None:
            return None
        try:
            return json.loads(valor)
        except (ValueError, TypeError):
            return None

    def cache_guardar(self, clave: str, valor: dict, ttl_s: int) -> None:
        # SET con EX: la clave SIEMPRE tiene TTL, nunca queda una entrada sin
        # vencimiento (se valida en validar_integridad.py del Hito 12).
        corte = cortocircuito.de(FUENTE)
        if not corte.permitir():
            return
        try:
            self._cli().set(clave, json.dumps(valor), ex=ttl_s)
        except Exception:
            corte.registrar_falla()
            logger.warning("redis cache no disponible (escritura) clave=%s", clave)

    def cerrar(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None


redis_adapter = RedisAdapter()
