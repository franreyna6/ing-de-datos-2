"""Pruebas de la demo en vivo (Hito 13) sin bases levantadas.

Se reemplazan los adaptadores por dobles en memoria que imitan el contrato de
cada base (IRIS con su maquina de estados, Neo4j, InfluxDB, MongoDB y Redis).
Se verifica la ORQUESTACION: que IRIS decide, que un rechazo de regla es 409
(y no 503), que la propagacion fallida queda a la vista en la traza, que el
tablero aisla una base caida y que solo se escriben partidos de laboratorio.

Ejecutar:  pytest tests/test_vivo.py -v
"""
import pytest
from fastapi.testclient import TestClient

from app.adapters.cassandra_adapter import cassandra_adapter
from app.adapters.influx_adapter import influx_adapter
from app.adapters.iris_adapter import iris_adapter
from app.adapters.mongo_adapter import mongo_adapter
from app.adapters.neo4j_adapter import neo4j_adapter
from app.adapters.redis_adapter import redis_adapter
from app.core.errores import ErrorDependencia
from app.main import app

cliente = TestClient(app, raise_server_exceptions=False)
COD = "H13-DEMO-URUARG"


class IrisFalso:
    """Imita Fixture.Vivo: Programado -> EnJuego -> Finalizado y sus reglas."""

    def __init__(self):
        self.p = {}

    def __call__(self, metodo, *args):
        if metodo == "Crear":
            codigo, local, visit, sede, fecha = args
            self.p[codigo] = {"ok": True, "codigo": codigo, "estado": "Programado",
                              "golesLocal": 0, "golesVisitante": 0, "equipoLocal": local,
                              "equipoVisitante": visit, "sede": "Estadio Centenario",
                              "fecha": fecha, "cantidadEventos": 0,
                              "terna": [{"rol": "Principal", "arbitro": "Wilton Sampaio",
                                         "nacionalidad": "BRA"}]}
            return dict(self.p[codigo], accion="creado")
        codigo = args[0]
        p = self.p.get(codigo)
        if p is None:
            return {"ok": False, "codigo": codigo, "motivo": f"No existe el partido {codigo}"}
        if metodo == "Estado":
            return dict(p)
        if metodo == "Iniciar":
            if p["estado"] != "Programado":
                return dict(p, ok=False, motivo="Transicion ilegal")
            p["estado"] = "EnJuego"
        elif metodo == "Finalizar":
            if p["estado"] != "EnJuego":
                return dict(p, ok=False, motivo="Transicion ilegal")
            p["estado"] = "Finalizado"
        elif metodo == "RegistrarEvento":
            _, evento, tipo, minuto, jugador = args
            if p["estado"] != "EnJuego":
                return dict(p, ok=False, motivo=f"el partido {codigo} esta {p['estado']} "
                                                "y no admite eventos")
            p["cantidadEventos"] += 1
            if tipo == "Gol":
                lado = "golesLocal" if jugador.startswith(p["equipoLocal"]) else "golesVisitante"
                p[lado] += 1
        return dict(p, ok=True)


@pytest.fixture
def dobles(monkeypatch):
    iris = IrisFalso()
    estado_redis, hll, sesiones = {}, {}, {}
    eventos = []
    monkeypatch.setattr(iris_adapter, "vivo", iris)
    monkeypatch.setattr(neo4j_adapter, "crear_partido_lab",
                        lambda *a: {"codigo": a[0], "local": "Uruguay", "visitante": "Argentina",
                                    "sede": "Estadio Centenario", "ciudad": "Montevideo"})

    def registrar(partido, ev, tipo, minuto, jugador, gl, gv):
        eventos.append({"evento": ev, "tipo": tipo, "minuto": minuto, "jugadorCodigo": jugador,
                        "jugadorNombre": "Jugador " + jugador})
        return {"evento": ev, "jugador": "x", "equipo": jugador[:3]}
    monkeypatch.setattr(neo4j_adapter, "registrar_evento", registrar)
    monkeypatch.setattr(neo4j_adapter, "eventos_de_partido",
                        lambda c, limit: {"partido": c, "fecha": None, "eventos": list(eventos)})

    def guardar(c, e, ttl_s=0):
        estado_redis.setdefault(c, {}).update({k: str(v) for k, v in e.items()})
        return True
    monkeypatch.setattr(redis_adapter, "vivo_guardar_estado", guardar)
    monkeypatch.setattr(redis_adapter, "vivo_leer",
                        lambda c: {"estado": estado_redis.get(c, {}),
                                   "hinchasUnicos": len(hll.get(c, set()))})

    def crear_sesion(sid, uid, rol, ttl, partido=None):
        sesiones[sid] = uid
        if partido:
            hll.setdefault(partido, set()).add(uid)
        return {"sesionId": sid, "usuarioId": uid, "estado": "activa", "ttlSegundos": ttl}
    monkeypatch.setattr(redis_adapter, "crear_sesion", crear_sesion)
    monkeypatch.setattr(redis_adapter, "renovar_sesion",
                        lambda sid, ttl: None if sid not in sesiones else
                        {"sesionId": sid, "usuarioId": sesiones[sid], "estado": "activa",
                         "ttlSegundos": ttl, "acciones": 1})
    monkeypatch.setattr(redis_adapter, "cache_leer", lambda clave: None)
    monkeypatch.setattr(redis_adapter, "cache_guardar", lambda *a: None)
    monkeypatch.setattr(cassandra_adapter, "leer_comentarios",
                        lambda p, i, l: {"partido": p, "ventana": "2030-06-08T20:20:00+00:00",
                                         "comentarios": []})
    escritos = []
    monkeypatch.setattr(influx_adapter, "escribir_estadisticas",
                        lambda p, s, g, puntos: escritos.extend(puntos) or len(puntos))
    monkeypatch.setattr(influx_adapter, "serie_agregada", lambda *a: [
        {"ventana": "t", "equipoId": "URU", "posesionPct": 55.0, "pasesAcum": 10, "tirosAcum": 1}])
    monkeypatch.setattr(mongo_adapter, "obtener_equipo",
                        lambda c: {"codigo": c, "nombre": c, "confederacion": "CONMEBOL"})
    return {"iris": iris, "eventos": eventos, "escritos": escritos, "estado": estado_redis}


def _crear():
    return cliente.post("/vivo/partidos", json={"local": "URU", "visitante": "ARG",
                                                "sede": "CENT", "fecha": "2030-06-08"})


def test_ciclo_completo_del_partido(dobles):
    r = _crear()
    assert r.status_code == 201, r.text
    assert r.json()["partido"]["estado"] == "Programado"
    assert [p["fuente"] for p in r.json()["traza"]] == ["iris", "neo4j", "redis"]
    assert cliente.post(f"/vivo/partidos/{COD}/iniciar").json()["partido"]["estado"] == "EnJuego"
    g = cliente.post(f"/vivo/partidos/{COD}/eventos",
                     json={"tipo": "Gol", "minuto": 23, "jugadorCodigo": "URU-4-blpv45"})
    assert g.status_code == 201, g.text
    assert g.json()["partido"]["golesLocal"] == 1
    assert len(dobles["eventos"]) == 1                      # llego al grafo
    assert dobles["estado"][COD]["golesLocal"] == "1"       # y a Redis
    assert cliente.post(f"/vivo/partidos/{COD}/finalizar").json()["partido"]["estado"] == "Finalizado"


def test_regla_de_iris_es_409_y_no_toca_el_grafo(dobles):
    _crear()
    r = cliente.post(f"/vivo/partidos/{COD}/eventos",
                     json={"tipo": "Gol", "minuto": 10, "jugadorCodigo": "URU-4-blpv45"})
    assert r.status_code == 409
    assert r.json()["error"]["detalles"]["code"] == "BUSINESS_RULE"
    assert "no admite eventos" in r.json()["error"]["detalles"]["motivo"]
    assert dobles["eventos"] == []                          # Neo4j no recibio nada


def test_propagacion_fallida_queda_en_la_traza(dobles, monkeypatch):
    _crear()
    cliente.post(f"/vivo/partidos/{COD}/iniciar")

    def neo4j_caido(*a):
        raise ErrorDependencia("neo4j", "conexion rechazada")
    monkeypatch.setattr(neo4j_adapter, "registrar_evento", neo4j_caido)
    r = cliente.post(f"/vivo/partidos/{COD}/eventos",
                     json={"tipo": "Gol", "minuto": 50, "jugadorCodigo": "ARG-9-3uidfj"})
    assert r.status_code == 201                             # IRIS (fuente de verdad) lo acepto
    neo = [p for p in r.json()["traza"] if p["fuente"] == "neo4j"][0]
    assert neo["ok"] is False and neo["sincronizado"] is False


def test_solo_partidos_de_laboratorio(dobles):
    r = cliente.post(f"/vivo/partidos/F2030-001/iniciar")
    assert r.status_code == 400
    r = cliente.post("/vivo/partidos", json={"codigo": "F2030-001", "local": "URU",
                                             "visitante": "ARG", "sede": "CENT",
                                             "fecha": "2030-06-08"})
    assert r.status_code == 400


def test_tablero_aisla_una_base_caida(dobles, monkeypatch):
    _crear()

    def influx_caido(*a):
        raise ErrorDependencia("influxdb", "timeout")
    monkeypatch.setattr(influx_adapter, "serie_agregada", influx_caido)
    t = cliente.get(f"/vivo/partidos/{COD}/tablero")
    assert t.status_code == 200
    s = t.json()["secciones"]
    assert s["estadisticas"]["ok"] is False and s["estadisticas"]["http"] == 503
    for nombre in ("partido", "eventos", "comentarios", "vivo", "equipos"):
        assert s[nombre]["ok"] is True, nombre
    assert s["equipos"]["datos"]["local"]["codigo"] == "URU"  # equipos tomados de IRIS


def test_estadisticas_y_validacion(dobles):
    ok = cliente.post(f"/vivo/partidos/{COD}/estadisticas", json={"sede": "CENT", "puntos": [
        {"equipoId": "URU", "posesionPct": 55.5, "pasesAcum": 10, "tirosAcum": 1,
         "recuperacionesAcum": 2}]})
    assert ok.status_code == 201 and ok.json()["puntosEscritos"] == 1
    assert dobles["escritos"][0]["ts"] > 0                  # timestamp asignado
    mal = cliente.post(f"/vivo/partidos/{COD}/estadisticas", json={"sede": "CENT", "puntos": [
        {"equipoId": "URU", "posesionPct": 150, "pasesAcum": 10, "tirosAcum": 1,
         "recuperacionesAcum": 2}]})
    assert mal.status_code == 400


def test_sesion_ttl_deslizante_y_hll(dobles):
    s = cliente.post("/sesiones", json={"usuarioId": "u-1", "partido": COD})
    assert s.status_code == 201 and s.json()["ttlSegundos"] == 1800
    a = cliente.post(f"/sesiones/{s.json()['sesionId']}/actividad")
    assert a.status_code == 200 and a.json()["ttlSegundos"] == 1800
    assert cliente.post("/sesiones/s-inexistente/actividad").status_code == 404
    t = cliente.get(f"/vivo/partidos/{COD}/tablero?local=URU&visitante=ARG")
    assert t.json()["secciones"]["vivo"]["datos"]["hinchasUnicos"] == 1


def test_demo_html_y_metricas_no_cuentan_estaticos():
    assert cliente.get("/demo/").status_code == 200
    cliente.get("/demo/")
    assert 'ruta="/demo' not in cliente.get("/metrics").text
