"""Pruebas unitarias del contrato y el manejo de errores (RF15).

No necesitan ninguna base levantada: verifican validacion previa, formato de
error comun, request-id y la distincion ausencia/dependencia. Con las bases
apagadas, las fuentes responden 503 controlado, que es justamente uno de los
escenarios que el hito pide demostrar (dependencia no disponible).

Ejecutar:  pytest tests/ -v
"""
import datetime as dt

from fastapi.testclient import TestClient

from app.main import app
from app.adapters.cassandra_adapter import ventana_de

cliente = TestClient(app, raise_server_exceptions=False)


def test_openapi_lista_las_rutas():
    spec = app.openapi()
    rutas = spec["paths"]
    assert "/equipos/{codigo}" in rutas
    assert "/partidos/{codigo}/comentarios" in rutas
    assert "/sesiones/{sesion_id}" in rutas
    # El contrato debe declarar el metodo POST de comentarios (escritura).
    assert "post" in rutas["/partidos/{codigo}/comentarios"]


def test_salud_responde_200_con_dependencias():
    r = cliente.get("/salud")
    assert r.status_code == 200
    fuentes = {d["fuente"] for d in r.json()["dependencias"]}
    assert fuentes == {"mongodb", "neo4j", "cassandra", "redis", "influxdb", "iris"}


def test_request_id_vuelve_en_header():
    r = cliente.get("/salud")
    assert "x-request-id" in {k.lower() for k in r.headers}


def test_validacion_limit_invalido_no_consulta_la_base():
    # limit=0 debe rechazarse con 400 antes de tocar Mongo (RNF3).
    r = cliente.get("/equipos/ARG/jugadores?limit=0")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_validacion_fechas_invertidas_en_estadisticas():
    r = cliente.get("/partidos/F1/estadisticas"
                    "?desde=2030-06-13T10:00:00Z&hasta=2030-06-13T09:00:00Z")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_formato_de_error_es_consistente():
    # Toda respuesta de error tiene error.code, error.message y error.request_id.
    r = cliente.get("/equipos/ARG/jugadores?limit=0")
    err = r.json()["error"]
    assert {"code", "message", "request_id"} <= set(err.keys())


def test_dependencia_caida_devuelve_503_no_200():
    # Sin Mongo levantado, el endpoint responde 503 (no 200 vacio, no 500).
    r = cliente.get("/equipos/ARG")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    # El cuerpo NO expone la causa tecnica interna (RF12).
    assert "pymongo" not in r.text.lower()


def test_ventana_cassandra_trunca_a_5_minutos():
    # La regla de bucketing debe coincidir con la del Hito 6.
    inst = dt.datetime(2030, 6, 22, 20, 23, 41, tzinfo=dt.timezone.utc)
    assert ventana_de(inst) == dt.datetime(2030, 6, 22, 20, 20, 0, tzinfo=dt.timezone.utc)


def test_sesion_inexistente_sin_redis_es_dependencia():
    # Con Redis apagado, cualquier sesion devuelve 503 (no 404): la base no respondio.
    r = cliente.get("/sesiones/no-existe")
    assert r.status_code == 503
