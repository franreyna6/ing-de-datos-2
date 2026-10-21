"""Adaptador tabular: Cassandra (Hito 6) — comentarios por partido.

Unico lugar que conoce el cliente de Cassandra (RNF5). Respeta el patron de
particion del Hito 6: la tabla comentarios_por_partido tiene PRIMARY KEY
((partido_id, ventana), creado_en DESC, comentario_id). La clave de particion es
(partido_id, ventana), donde 'ventana' es el inicio UTC del bucket de 5 minutos
que contiene al comentario.

Por eso la API NO acepta filtros libres: el endpoint siempre deriva la ventana a
partir de un instante (query param) y lee UNA particion con LIMIT. Nunca usa
ALLOW FILTERING (la clase y el Hito 6 lo prohiben como diseno).

Escritura (POST): la clave incluye comentario_id (UUID). Si el cliente reintenta
sin reusar el mismo id, se crea otro comentario (no es idempotente por defecto);
por eso el endpoint acepta una clave de idempotencia opcional. Ver docs.

Dos clientes posibles (Clase 11: "el driver o cliente de cada motor"):
  * Preferido: el driver nativo de Cassandra (cassandra-driver), con prepared
    statements parametrizados.
  * Alternativa automatica: cqlsh, el cliente oficial de Cassandra, ejecutado
    dentro del contenedor del Hito 6. Se usa SOLO cuando el driver nativo no
    puede cargar en la maquina (incompatibilidad conocida de cassandra-driver
    con Python 3.12, que removio el modulo asyncore del que dependia el reactor
    por defecto). En ese modo las entradas del cliente se escapan para CQL (no se
    concatenan crudas), igual que la regla de parametrizacion que aplicamos en
    Neo4j.
El modo se decide una sola vez por sesion y la API no cambia su contrato: el
endpoint, los datos y los errores son los mismos use el cliente que use.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import uuid

from app.core.config import obtener_config
from app.core.errores import ErrorDependencia
from app.core.registro import logger

FUENTE = "cassandra"
VENTANA_MIN = 5  # minutos por bucket, igual que el Hito 6

# partido_id proviene de la ruta HTTP. Se valida con un patron estricto antes de
# usarlo en cqlsh, para no depender solo del escape (defensa en profundidad).
_PATRON_PARTIDO = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def ventana_de(instante: dt.datetime) -> dt.datetime:
    """Trunca un instante UTC al inicio de su ventana de 5 minutos.

    Es la MISMA regla que usa la carga del Hito 6, para que la API lea la
    particion correcta. Ej: 20:23:41 -> 20:20:00.
    """
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=dt.timezone.utc)
    instante = instante.astimezone(dt.timezone.utc)
    minuto_bucket = (instante.minute // VENTANA_MIN) * VENTANA_MIN
    return instante.replace(minute=minuto_bucket, second=0, microsecond=0)


def _esc(valor: str) -> str:
    """Escapa un literal de texto para CQL duplicando las comillas simples.

    Es la forma estandar de citar strings en CQL ('O''Brien'). Se usa solo en el
    modo cqlsh; el modo driver usa parametros (?) y no necesita escape.
    """
    return str(valor).replace("'", "''")


def _ts_cql(momento: dt.datetime) -> str:
    """Formatea un timestamp UTC como literal aceptado por CQL."""
    return momento.strftime("%Y-%m-%d %H:%M:%S+0000")


def _parse_ts(texto: str | None) -> str | None:
    """Convierte un timestamp devuelto por 'SELECT JSON' a ISO-8601 UTC."""
    if not texto:
        return None
    for formato in ("%Y-%m-%d %H:%M:%S.%fZ", "%Y-%m-%d %H:%M:%SZ",
                    "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            m = dt.datetime.strptime(texto, formato).replace(tzinfo=dt.timezone.utc)
            return m.isoformat()
        except ValueError:
            continue
    return texto  # si el formato no coincide, se devuelve tal cual (no se pierde el dato)


class CassandraAdapter:
    def __init__(self) -> None:
        self._cfg = obtener_config()
        self._modo: str | None = None   # None | "driver" | "cqlsh"
        self._cluster = None
        self._session = None
        self._ps_leer = None
        self._ps_escribir = None

    # ------------------------------------------------------------------ modo
    def _asegurar_modo(self) -> None:
        """Decide una sola vez que cliente usar. Prefiere el driver nativo."""
        if self._modo is not None:
            return
        try:
            from cassandra.cluster import Cluster  # noqa: F401
            self._modo = "driver"
        except Exception as e:  # ImportError / DependencyException / etc.
            logger.warning(
                "cassandra: driver nativo no disponible (%s); se usa cqlsh",
                e.__class__.__name__)
            self._modo = "cqlsh"

    # ------------------------------------------------------- cliente: driver
    def _ses(self):
        if self._session is None:
            from cassandra.cluster import Cluster
            self._cluster = Cluster(
                [self._cfg.cassandra_host], port=self._cfg.cassandra_port,
                connect_timeout=self._cfg.dep_timeout_s,
            )
            self._session = self._cluster.connect(self._cfg.cassandra_keyspace)
            self._session.default_timeout = self._cfg.dep_timeout_s
            # Prepared statements: compilados una vez, parametrizados (seguro y rapido).
            self._ps_leer = self._session.prepare(
                "SELECT creado_en, comentario_id, usuario_id, contenido, estado, likes "
                "FROM comentarios_por_partido "
                "WHERE partido_id = ? AND ventana = ? LIMIT ?")
            self._ps_escribir = self._session.prepare(
                "INSERT INTO comentarios_por_partido "
                "(partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes) "
                "VALUES (?, ?, ?, ?, ?, ?, 'visible', 0)")
        return self._session

    # -------------------------------------------------------- cliente: cqlsh
    def _cqlsh(self, cql: str) -> str:
        """Ejecuta una sentencia CQL con cqlsh dentro del contenedor del Hito 6.

        No usa shell (args como lista) y el CQL ya viene con literales escapados.
        Un fallo (docker/cqlsh ausente, timeout, exit != 0) se propaga como
        excepcion para que la capa superior lo traduzca a 503.
        """
        cmd = ["docker", "exec", self._cfg.cassandra_container,
               "cqlsh", "-k", self._cfg.cassandra_keyspace, "-e", cql]
        # Margen sobre el timeout de dependencia: docker exec + arranque de cqlsh
        # agregan overhead propio del cliente, ajeno a la latencia de la base.
        res = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=self._cfg.dep_timeout_s + 12)
        if res.returncode != 0:
            raise RuntimeError((res.stderr or res.stdout or "cqlsh fallo").strip())
        return res.stdout

    @staticmethod
    def _filas_json(salida: str) -> list[dict]:
        """Extrae las filas de la salida de 'SELECT JSON ...' de cqlsh.

        cqlsh imprime una columna [json] con un objeto JSON por fila, mas lineas
        de cabecera/separador/'(N rows)' que se ignoran.
        """
        filas = []
        for linea in salida.splitlines():
            t = linea.strip()
            if t.startswith("{") and t.endswith("}"):
                try:
                    filas.append(json.loads(t))
                except json.JSONDecodeError:
                    continue
        return filas

    def _leer_cqlsh(self, partido_id: str, ventana: dt.datetime, limit: int) -> list[dict]:
        cql = (
            "SELECT JSON creado_en, comentario_id, usuario_id, contenido, estado, likes "
            "FROM comentarios_por_partido "
            f"WHERE partido_id = '{_esc(partido_id)}' AND ventana = '{_ts_cql(ventana)}' "
            f"LIMIT {int(limit)}")
        filas = self._filas_json(self._cqlsh(cql))
        return [{
            "comentarioId": f.get("comentario_id"),
            "creadoEn": _parse_ts(f.get("creado_en")),
            "usuarioId": f.get("usuario_id"),
            "contenido": f.get("contenido"),
            "estado": f.get("estado"),
            "likes": f.get("likes"),
        } for f in filas]

    def _escribir_cqlsh(self, partido_id: str, ventana: dt.datetime, creado_en: dt.datetime,
                        cid: uuid.UUID, usuario_id: str, contenido: str) -> None:
        cql = (
            "INSERT INTO comentarios_por_partido "
            "(partido_id, ventana, creado_en, comentario_id, usuario_id, contenido, estado, likes) "
            f"VALUES ('{_esc(partido_id)}', '{_ts_cql(ventana)}', '{_ts_cql(creado_en)}', "
            f"{cid}, '{_esc(usuario_id)}', '{_esc(contenido)}', 'visible', 0)")
        self._cqlsh(cql)

    # ---------------------------------------------------------------- API
    def verificar(self) -> bool:
        try:
            self._asegurar_modo()
            if self._modo == "driver":
                self._ses().execute("SELECT release_version FROM system.local")
            else:
                self._cqlsh("SELECT release_version FROM system.local")
            return True
        except Exception:
            return False

    def leer_comentarios(self, partido_id: str, instante: dt.datetime,
                         limit: int) -> dict:
        """Lee una ventana (particion) de comentarios de un partido."""
        if not _PATRON_PARTIDO.match(partido_id):
            # Defensa en profundidad: la ruta ya acota el formato, pero el
            # adaptador no confia en entradas sin validar antes de ir a cqlsh.
            raise ErrorDependencia(FUENTE, "partido_id con formato no permitido")
        v = ventana_de(instante)
        self._asegurar_modo()
        try:
            if self._modo == "driver":
                filas = self._ses().execute(self._ps_leer, (partido_id, v, limit))
                res = [{
                    "comentarioId": str(f.comentario_id),
                    "creadoEn": f.creado_en.isoformat() if f.creado_en else None,
                    "usuarioId": f.usuario_id,
                    "contenido": f.contenido,
                    "estado": f.estado,
                    "likes": f.likes,
                } for f in filas]
            else:
                res = self._leer_cqlsh(partido_id, v, limit)
        except Exception as e:
            logger.warning("cassandra leer error partido=%s", partido_id)
            raise ErrorDependencia(FUENTE, str(e))
        logger.info("cassandra leer partido=%s ventana=%s filas=%s modo=%s",
                    partido_id, v, len(res), self._modo)
        return {"partido": partido_id, "ventana": v.isoformat(), "comentarios": res}

    def escribir_comentario(self, partido_id: str, usuario_id: str, contenido: str,
                            comentario_id: str | None = None) -> dict:
        """Inserta un comentario. La ventana se deriva del instante de creacion.

        comentario_id puede venir del cliente (clave de idempotencia): reinsertar
        el mismo id sobre la misma clave reescribe la misma fila (upsert), no la
        duplica. Si no se envia, se genera uno nuevo.
        """
        if not _PATRON_PARTIDO.match(partido_id):
            raise ErrorDependencia(FUENTE, "partido_id con formato no permitido")
        ahora = dt.datetime.now(dt.timezone.utc)
        v = ventana_de(ahora)
        try:
            cid = uuid.UUID(comentario_id) if comentario_id else uuid.uuid4()
        except ValueError as e:
            # comentario_id con formato invalido: no es culpa de la base.
            raise ErrorDependencia(FUENTE, f"comentario_id invalido: {e}")
        self._asegurar_modo()
        try:
            if self._modo == "driver":
                self._ses().execute(self._ps_escribir,
                                    (partido_id, v, ahora, cid, usuario_id, contenido))
            else:
                self._escribir_cqlsh(partido_id, v, ahora, cid, usuario_id, contenido)
        except Exception as e:
            logger.warning("cassandra escribir error partido=%s", partido_id)
            raise ErrorDependencia(FUENTE, str(e))
        logger.info("cassandra escribir partido=%s comentario=%s modo=%s",
                    partido_id, cid, self._modo)
        return {"partido": partido_id, "ventana": v.isoformat(),
                "comentarioId": str(cid), "creadoEn": ahora.isoformat()}

    def cerrar(self) -> None:
        if self._cluster is not None:
            self._cluster.shutdown()
            self._cluster = None
            self._session = None


cassandra_adapter = CassandraAdapter()
