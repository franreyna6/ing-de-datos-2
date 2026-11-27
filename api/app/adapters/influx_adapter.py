"""Adaptador temporal: InfluxDB 3 Core (Hito 8) — estadisticas en una ventana.

Unico lugar que conoce el cliente HTTP/SQL de InfluxDB 3 Core (RNF5). Habla por
HTTP contra /api/v3/query_sql, igual que los scripts del Hito 8, usando solo la
biblioteca estandar (http.client) para no sumar dependencias.

La consulta SQL es fija y acota SIEMPRE por partido y rango temporal [desde, hasta)
(RNF13). El rango se valida antes (orden y duracion maxima) en el servicio. El
token se lee del entorno (RNF7): si falta, se responde dependencia no disponible,
nunca se inventa.

Formato del cuerpo: {db, q, format}, igual que el cliente del Hito 8. InfluxDB 3
Core (/api/v3/query_sql) espera el SQL en el campo "q" (no "query"). Esta version
no acepta el campo "params" con marcadores $nombre (responde HTTP 400), asi que
los valores se inlinean ESCAPADOS y el partido se valida por patron antes de
construir el SQL (defensa en profundidad; no se concatena entrada cruda).

Measurement del Hito 8: estadisticas_equipo (dims: partido_id, equipo_id, sede,
grupo; fields acumulados).
"""
from __future__ import annotations

import http.client
import json
import re
from urllib.parse import urlparse

from app.core.config import obtener_config
from app.core.errores import ErrorDependencia
from app.core.registro import logger

FUENTE = "influxdb"

# partido_id proviene de la ruta HTTP. Se valida con un patron estricto antes de
# inlinearlo en el SQL (ademas del escape), para no depender solo del escape.
_PATRON_PARTIDO = re.compile(r"^[A-Za-z0-9_-]{1,40}$")

# SQL fijo: solo cambian partido, desde y hasta, que se inlinean escapados.
_SQL_TMPL = (
    "SELECT time, equipo_id, posesion_pct, pases_acum, tiros_acum, recuperaciones_acum "
    "FROM estadisticas_equipo "
    "WHERE partido_id = '{partido}' "
    "AND time >= '{desde}' AND time < '{hasta}' "
    "ORDER BY time"
)


def _esc(valor: str) -> str:
    """Escapa un literal de texto para SQL duplicando las comillas simples."""
    return str(valor).replace("'", "''")


class InfluxAdapter:
    def __init__(self) -> None:
        self._cfg = obtener_config()

    def _conn(self) -> http.client.HTTPConnection:
        u = urlparse(self._cfg.influx_url)
        return http.client.HTTPConnection(u.hostname, u.port or 8181,
                                          timeout=self._cfg.dep_timeout_s)

    def _consultar(self, sql: str) -> list[dict]:
        if not self._cfg.influx_token:
            # Sin token no se puede consultar; es una falla de dependencia/config.
            raise ErrorDependencia(FUENTE, "falta INFLUXDB3_TOKEN en el entorno")
        cuerpo = json.dumps({
            "db": self._cfg.influx_database,
            "q": sql,
            "format": "json",
        })
        headers = {
            "Authorization": f"Bearer {self._cfg.influx_token}",
            "Content-Type": "application/json",
        }
        conn = self._conn()
        try:
            conn.request("POST", "/api/v3/query_sql", body=cuerpo, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            if resp.status >= 400:
                # No filtrar el cuerpo crudo al cliente; va al log.
                logger.warning("influx status=%s detalle=%s", resp.status,
                               data[:200].decode("utf-8", "replace"))
                raise ErrorDependencia(FUENTE, f"HTTP {resp.status}")
            return json.loads(data) if data else []
        except ErrorDependencia:
            raise
        except Exception as e:
            logger.warning("influx error de conexion")
            raise ErrorDependencia(FUENTE, str(e))
        finally:
            conn.close()

    def verificar(self) -> bool:
        try:
            self._consultar("SELECT 1 AS ok")
            return True
        except Exception:
            return False

    def estadisticas(self, partido: str, desde_iso: str, hasta_iso: str) -> dict:
        """Puntos de estadisticas de un partido en [desde, hasta)."""
        if not _PATRON_PARTIDO.match(partido):
            raise ErrorDependencia(FUENTE, "partido con formato no permitido", conexion=False)
        sql = _SQL_TMPL.format(partido=_esc(partido), desde=_esc(desde_iso),
                               hasta=_esc(hasta_iso))
        filas = self._consultar(sql)
        puntos = [{
            "time": f.get("time"),
            "equipoId": f.get("equipo_id"),
            "posesionPct": f.get("posesion_pct"),
            "pasesAcum": f.get("pases_acum"),
            "tirosAcum": f.get("tiros_acum"),
            "recuperacionesAcum": f.get("recuperaciones_acum"),
        } for f in filas]
        logger.info("influx partido=%s puntos=%s", partido, len(puntos))
        return {"partido": partido, "desde": desde_iso, "hasta": hasta_iso,
                "puntos": puntos}


    # ------------------------------------------- Hito 13: demo en vivo (lectura agregada)
    def serie_agregada(self, partido: str, desde_iso: str, hasta_iso: str,
                       paso_s: int = 10) -> list[dict]:
        """Posesion promedio y acumulados por ventanas de paso_s segundos.

        Es el patron de acceso que justifica InfluxDB (Hito 8): rango de tiempo +
        agregacion con date_bin. AVG para la posesion (muestra) y MAX para los
        contadores acumulados (pases, tiros), igual que las agregaciones del Hito 8.
        """
        if not _PATRON_PARTIDO.match(partido):
            raise ErrorDependencia(FUENTE, "partido con formato no permitido", conexion=False)
        paso = max(1, min(int(paso_s), 300))
        sql = (
            f"SELECT date_bin(INTERVAL '{paso} seconds', time) AS ventana, equipo_id, "
            "AVG(posesion_pct) AS posesion, MAX(pases_acum) AS pases, MAX(tiros_acum) AS tiros "
            "FROM estadisticas_equipo "
            f"WHERE partido_id = '{_esc(partido)}' "
            f"AND time >= '{_esc(desde_iso)}' AND time < '{_esc(hasta_iso)}' "
            "GROUP BY ventana, equipo_id ORDER BY ventana")
        filas = self._consultar(sql)
        return [{"ventana": f.get("ventana"), "equipoId": f.get("equipo_id"),
                 "posesionPct": f.get("posesion"), "pasesAcum": f.get("pases"),
                 "tirosAcum": f.get("tiros")} for f in filas]

    # ------------------------------------------- Hito 13: demo en vivo (escritura)
    def escribir_estadisticas(self, partido: str, sede: str, grupo: str,
                              puntos: list[dict]) -> int:
        """Escribe puntos en estadisticas_equipo con line protocol (como el Hito 8).

        Mismo esquema del Hito 8: tags partido_id, equipo_id, sede, grupo (lo que
        se filtra) y fields numericos (lo que se mide). Precision: segundos.
        Devuelve la cantidad de puntos escritos.
        """
        if not _PATRON_PARTIDO.match(partido):
            raise ErrorDependencia(FUENTE, "partido con formato no permitido", conexion=False)
        if not self._cfg.influx_token:
            raise ErrorDependencia(FUENTE, "falta INFLUXDB3_TOKEN en el entorno")

        def _tag(v: str) -> str:
            # En line protocol las comas, espacios y '=' de un tag se escapan.
            return re.sub(r"([,= ])", r"\\\1", str(v))

        lineas = []
        for p in puntos:
            lineas.append(
                "estadisticas_equipo,partido_id=%s,equipo_id=%s,sede=%s,grupo=%s "
                "posesion_pct=%.1f,pases_acum=%di,tiros_acum=%di,recuperaciones_acum=%di %d"
                % (_tag(partido), _tag(p["equipoId"]), _tag(sede), _tag(grupo or "-"),
                   float(p["posesionPct"]), int(p["pasesAcum"]), int(p["tirosAcum"]),
                   int(p["recuperacionesAcum"]), int(p["ts"])))
        cuerpo = "\n".join(lineas)
        ruta = f"/api/v3/write_lp?db={self._cfg.influx_database}&precision=second"
        conn = self._conn()
        try:
            conn.request("POST", ruta, body=cuerpo.encode("utf-8"), headers={
                "Authorization": f"Bearer {self._cfg.influx_token}",
                "Content-Type": "text/plain; charset=utf-8"})
            resp = conn.getresponse()
            data = resp.read()
            if resp.status >= 400:
                logger.warning("influx write status=%s detalle=%s", resp.status,
                               data[:200].decode("utf-8", "replace"))
                raise ErrorDependencia(FUENTE, f"HTTP {resp.status}")
        except ErrorDependencia:
            raise
        except Exception as e:
            logger.warning("influx error de conexion (escritura)")
            raise ErrorDependencia(FUENTE, str(e))
        finally:
            conn.close()
        logger.info("influx escritura partido=%s puntos=%s", partido, len(lineas))
        return len(lineas)


influx_adapter = InfluxAdapter()
