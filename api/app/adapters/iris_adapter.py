"""Adaptador de objetos: InterSystems IRIS (Hito 9) — entidad compleja Partido.

Unico lugar que conoce el cliente de IRIS (RNF5). Para un endpoint de LECTURA, la
Clase 11 admite usar la proyeccion SQL de las clases persistentes: cada clase
%Persistent se ve como una tabla en el esquema SQL (aca, esquema 'Fixture'). Se
accede por el driver DB-API oficial de intersystems (paquete 'intersystems-irispython'),
que habla con el superserver en el puerto 1972.

Se consulta por el codigo de negocio (Partido.Codigo, p. ej. 'F2030-001') y se
arma un DTO estable: no se serializa toda la instancia ni detalles internos del
modelo de objetos que no formen parte del contrato. Un partido inexistente es un
404; IRIS caido es un 503.

Nota: este adaptador NO ejecuta transiciones de estado. Cambiar el estado de un
partido exige invocar los metodos de dominio (Iniciar/Finalizar) que validan la
transicion; eso excede el alcance de lectura de este hito y queda documentado.
"""
from __future__ import annotations

from app.core.config import obtener_config
from app.core.errores import ErrorDependencia
from app.core.registro import logger

FUENTE = "iris"

# SQL sobre la proyeccion de las clases del Hito 9. Parametrizado por codigo.
_SQL_PARTIDO = """
SELECT p.Codigo, p.Fecha, p.Fase, p.Estado,
       p.GolesLocal, p.GolesVisitante,
       local.Codigo AS LocalCodigo, visita.Codigo AS VisitaCodigo,
       s.Codigo AS SedeCodigo, s.Nombre AS SedeNombre
FROM Fixture.Partido p
  LEFT JOIN Fixture.Equipo local  ON p.EquipoLocal = local.ID
  LEFT JOIN Fixture.Equipo visita ON p.EquipoVisitante = visita.ID
  LEFT JOIN Fixture.Sede s        ON p.Sede = s.ID
WHERE p.Codigo = ?
"""

_SQL_EVENTOS = "SELECT COUNT(*) AS c FROM Fixture.Evento e JOIN Fixture.Partido p ON e.Partido = p.ID WHERE p.Codigo = ?"


class IrisAdapter:
    def __init__(self) -> None:
        self._cfg = obtener_config()
        self._conn = None

    def _conexion(self):
        if self._conn is None:
            import iris  # intersystems-irispython
            self._conn = iris.connect(
                self._cfg.iris_host, self._cfg.iris_port, self._cfg.iris_namespace,
                self._cfg.iris_user, self._cfg.iris_password,
                timeout=int(self._cfg.dep_timeout_s),
            )
        return self._conn

    def verificar(self) -> bool:
        try:
            cur = self._conexion().cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.close()
            return True
        except Exception:
            return False

    def detalle_partido(self, codigo: str) -> dict | None:
        """DTO de un partido (entidad compleja) o None si no existe."""
        try:
            cur = self._conexion().cursor()
            cur.execute(_SQL_PARTIDO, [codigo])
            fila = cur.fetchone()
            if fila is None:
                cur.close()
                logger.info("iris partido=%s inexistente", codigo)
                return None
            cols = [d[0].lower() for d in cur.description]
            reg = dict(zip(cols, fila))
            cur.execute(_SQL_EVENTOS, [codigo])
            cant_eventos = cur.fetchone()[0]
            cur.close()
        except Exception as e:
            logger.warning("iris error partido=%s", codigo)
            raise ErrorDependencia(FUENTE, str(e))
        logger.info("iris partido=%s detalle ok", codigo)
        return {
            "codigo": reg.get("codigo"),
            "fecha": str(reg.get("fecha")) if reg.get("fecha") is not None else None,
            "fase": reg.get("fase"),
            "estado": reg.get("estado"),
            "golesLocal": reg.get("goleslocal"),
            "golesVisitante": reg.get("golesvisitante"),
            "equipoLocal": reg.get("localcodigo"),
            "equipoVisitante": reg.get("visitacodigo"),
            "sede": {"codigo": reg.get("sedecodigo"), "nombre": reg.get("sedenombre")},
            "cantidadEventos": cant_eventos,
        }

    def cerrar(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


iris_adapter = IrisAdapter()
