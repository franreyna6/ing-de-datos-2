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

    # ------------------------------------------- Hito 13: demo en vivo (escritura)
    # Mismo modelo del Hito 7: la sesion es un HASH 'sesion:<id>' con TTL de
    # inactividad. Crear y renovar son operaciones atomicas en un pipeline
    # MULTI/EXEC (HSET + HINCRBY + EXPIRE): nunca leer-modificar-escribir.
    def crear_sesion(self, sesion_id: str, usuario_id: str, rol: str, ttl_s: int,
                     partido: str | None = None) -> dict:
        import datetime as _dt
        ahora = _dt.datetime.now(_dt.timezone.utc).isoformat()
        clave = f"sesion:{sesion_id}"
        try:
            pipe = self._cli().pipeline(transaction=True)
            pipe.hset(clave, mapping={"usuario_id": usuario_id, "rol": rol,
                                      "estado": "activa", "creada_en": ahora,
                                      "ultimo_acceso": ahora, "acciones": 0,
                                      "partido": partido or ""})
            pipe.expire(clave, ttl_s)
            if partido:
                # HyperLogLog: hinchas UNICOS conectados al partido con ~12 KB
                # fijos, sin importar si son 100 o 3 millones (error ~0,8 %).
                pipe.pfadd(f"vivo:hinchas:{partido}", usuario_id)
                pipe.expire(f"vivo:hinchas:{partido}", 6 * 3600)
            pipe.execute()
        except Exception as e:
            logger.warning("redis error crear sesion=%s", sesion_id)
            raise ErrorDependencia(FUENTE, str(e))
        return {"sesionId": sesion_id, "usuarioId": usuario_id, "estado": "activa",
                "ttlSegundos": ttl_s}

    def renovar_sesion(self, sesion_id: str, ttl_s: int) -> dict | None:
        """TTL deslizante: cada accion del usuario vuelve a poner el TTL completo.

        Devuelve None si la sesion ya vencio (404): una sesion vencida NO se
        resucita con una accion; el usuario se vuelve a autenticar.
        """
        import datetime as _dt
        clave = f"sesion:{sesion_id}"
        try:
            if not self._cli().exists(clave):
                return None
            pipe = self._cli().pipeline(transaction=True)
            pipe.hincrby(clave, "acciones", 1)
            pipe.hset(clave, "ultimo_acceso", _dt.datetime.now(_dt.timezone.utc).isoformat())
            pipe.expire(clave, ttl_s)
            pipe.hget(clave, "usuario_id")
            acciones, _, _, usuario = pipe.execute()
        except Exception as e:
            logger.warning("redis error renovar sesion=%s", sesion_id)
            raise ErrorDependencia(FUENTE, str(e))
        return {"sesionId": sesion_id, "usuarioId": usuario, "estado": "activa",
                "ttlSegundos": ttl_s, "acciones": int(acciones)}

    def vivo_guardar_estado(self, partido: str, estado: dict, ttl_s: int = 6 * 3600) -> bool:
        """Estado efimero del partido en vivo (minuto, marcador) para el tablero.

        La fuente de verdad del estado y del marcador es IRIS; esto es una copia
        rapida para leer en cada refresco sin ir a IRIS. Si Redis no responde,
        no se rompe la operacion: se registra y se sigue (igual que la cache).
        """
        clave = f"vivo:partido:{partido}"
        corte = cortocircuito.de(FUENTE)
        if not corte.permitir():
            return False
        try:
            pipe = self._cli().pipeline(transaction=True)
            pipe.hset(clave, mapping={k: ("" if v is None else str(v)) for k, v in estado.items()})
            pipe.expire(clave, ttl_s)
            pipe.execute()
        except Exception:
            corte.registrar_falla()
            logger.warning("redis no disponible (estado vivo) partido=%s", partido)
            return False
        corte.registrar_exito()
        return True

    def vivo_leer(self, partido: str) -> dict:
        """Estado en vivo + hinchas unicos (HyperLogLog). Lanza 503 si Redis cae."""
        try:
            pipe = self._cli().pipeline(transaction=False)
            pipe.hgetall(f"vivo:partido:{partido}")
            pipe.pfcount(f"vivo:hinchas:{partido}")
            estado, hinchas = pipe.execute()
        except Exception as e:
            raise ErrorDependencia(FUENTE, str(e))
        return {"estado": estado or {}, "hinchasUnicos": int(hinchas or 0)}

    def cerrar(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None


redis_adapter = RedisAdapter()
