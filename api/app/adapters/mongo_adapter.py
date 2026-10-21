"""Adaptador documental: MongoDB (Hito 4) — equipos y jugadores.

Unico lugar de la API que conoce el driver de MongoDB (RNF5). Encapsula:
  - creacion/reuso de la conexion (perezosa: se abre al primer uso);
  - seleccion de la database configurada;
  - ejecucion de la consulta documental con proyeccion y limite;
  - traduccion de errores del driver a ErrorDependencia;
  - conversion del documento al modelo interno (dict simple), sin devolver _id
    ni campos internos que el contrato no declara.

El driver (pymongo) se importa de forma PEREZOSA dentro de los metodos: asi la
API puede arrancar aunque este driver no este instalado o Mongo no este
levantado, y esa fuente se reporta como no disponible (503) en vez de impedir
el arranque de toda la aplicacion.

Patron de acceso (RNF13): busqueda por _id (codigo de negocio, p. ej. 'ARG') y
filtro+paginacion de jugadores por equipoCodigo, que son los indices que creo el
Hito 4. No hay escaneos sin criterio.
"""
from __future__ import annotations

from app.core.config import obtener_config
from app.core.errores import ErrorDependencia
from app.core.registro import logger

FUENTE = "mongodb"


class MongoAdapter:
    def __init__(self) -> None:
        self._cfg = obtener_config()
        self._client = None

    def _db(self):
        """Conexion perezosa y reutilizada. El timeout evita esperas infinitas (RNF8)."""
        if self._client is None:
            try:
                from pymongo import MongoClient
            except ImportError as e:
                raise ErrorDependencia(FUENTE, f"driver pymongo no instalado: {e}")
            ms = int(self._cfg.dep_timeout_s * 1000)
            self._client = MongoClient(
                self._cfg.mongodb_uri,
                serverSelectionTimeoutMS=ms,
                connectTimeoutMS=ms,
                socketTimeoutMS=ms,
            )
        return self._client[self._cfg.mongodb_db]

    def verificar(self) -> bool:
        """Ping para el chequeo de salud. True si responde; no lanza."""
        try:
            self._db().command("ping")
            return True
        except Exception:
            return False

    def obtener_equipo(self, codigo: str) -> dict | None:
        """Documento de un equipo por codigo, proyectado. None si no existe."""
        proyeccion = {"_id": 0, "codigo": "$_id", "nombre": 1, "confederacion": 1,
                      "rankingFIFA": 1, "grupo": 1, "ciudadSede": 1}
        try:
            doc = self._db().equipos.find_one({"_id": codigo}, proyeccion)
        except ErrorDependencia:
            raise
        except Exception as e:
            logger.warning("mongo equipo error codigo=%s", codigo)
            raise ErrorDependencia(FUENTE, str(e))
        logger.info("mongo equipo codigo=%s encontrado=%s", codigo, bool(doc))
        return doc

    def listar_jugadores(self, equipo_codigo: str, posicion: str | None,
                         limit: int, offset: int) -> list[dict]:
        """Jugadores de un equipo, con filtro opcional por posicion y paginacion."""
        filtro: dict = {"equipoCodigo": equipo_codigo}
        if posicion:
            filtro["posicion"] = posicion
        proyeccion = {"_id": 0, "codigo": "$_id", "nombre": 1, "apellido": 1,
                      "posicion": 1, "dorsal": 1, "equipoCodigo": 1}
        try:
            cursor = (self._db().jugadores
                      .find(filtro, proyeccion)
                      .sort("dorsal", 1)
                      .skip(offset)
                      .limit(limit))
            filas = list(cursor)
        except ErrorDependencia:
            raise
        except Exception as e:
            logger.warning("mongo jugadores error equipo=%s", equipo_codigo)
            raise ErrorDependencia(FUENTE, str(e))
        logger.info("mongo jugadores equipo=%s filas=%s", equipo_codigo, len(filas))
        return filas

    def cerrar(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


# Instancia unica reutilizada por los servicios (una conexion por proceso).
mongo_adapter = MongoAdapter()
