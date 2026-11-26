"""Pruebas de las metricas de Prometheus (Hito 13, RF4).

Como las del Hito 10, no necesitan ninguna base levantada: con las bases
apagadas las fuentes responden 503 controlado, y eso tambien se tiene que ver
en las metricas (errores contados, duracion de la dependencia con resultado
'error').

Ejecutar:  pytest tests/ -v
"""
import re

from fastapi.testclient import TestClient

from app.core import metricas
from app.main import app

cliente = TestClient(app, raise_server_exceptions=False)


def _valor(texto: str, nombre: str, **etiquetas) -> float:
    """Busca una serie en el texto de /metrics y devuelve su valor (0 si no esta)."""
    for linea in texto.splitlines():
        if not linea.startswith(nombre + "{"):
            continue
        if all(f'{k}="{v}"' in linea for k, v in etiquetas.items()):
            return float(linea.rsplit(" ", 1)[1])
    return 0.0


def test_metrics_responde_en_formato_prometheus():
    r = cliente.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "# TYPE fixture_api_requests_total counter" in r.text
    assert "# TYPE fixture_api_request_duration_seconds histogram" in r.text


def test_metrics_no_aparece_en_el_contrato_openapi():
    assert "/metrics" not in app.openapi()["paths"]


def test_request_se_cuenta_con_la_plantilla_de_ruta_y_no_con_la_url():
    antes = _valor(cliente.get("/metrics").text, "fixture_api_requests_total",
                   metodo="GET", ruta="/equipos/{codigo}/jugadores", estado="400")
    cliente.get("/equipos/ARG/jugadores?limit=0")      # 400 de validacion
    cliente.get("/equipos/BRA/jugadores?limit=0")      # otro codigo, misma plantilla
    texto = cliente.get("/metrics").text
    despues = _valor(texto, "fixture_api_requests_total",
                     metodo="GET", ruta="/equipos/{codigo}/jugadores", estado="400")
    assert despues - antes == 2
    assert 'ruta="/equipos/ARG/jugadores"' not in texto   # cardinalidad controlada


def test_ruta_inexistente_se_agrupa_en_sin_ruta():
    cliente.get("/no-existe/12345")
    assert 'ruta="sin_ruta"' in cliente.get("/metrics").text


def test_metrics_no_se_mide_a_si_misma():
    cliente.get("/metrics")
    assert 'ruta="/metrics"' not in cliente.get("/metrics").text


def test_dependencia_caida_queda_medida_con_resultado_error():
    # Sin bases levantadas, el adaptador de Mongo falla: la API responde 503 y
    # la duracion de la llamada queda registrada con resultado="error".
    # Si otro test ya abrio el corte rapido de Mongo, la llamada queda como
    # resultado="cortocircuito" (no se intento): cuenta igual como falla medida.
    r = cliente.get("/equipos/ARG")
    assert r.status_code == 503
    texto = cliente.get("/metrics").text
    fallas = sum(_valor(texto, "fixture_dependencia_duration_seconds_count",
                        fuente="mongodb", operacion="obtener_equipo", resultado=res)
                 for res in ("error", "cortocircuito"))
    assert fallas >= 1
    assert _valor(texto, "fixture_api_requests_total",
                  metodo="GET", ruta="/equipos/{codigo}", estado="503") >= 1


def test_etiqueta_partido_controla_la_cardinalidad():
    assert metricas.etiqueta_partido("F2030-063") == "F2030-063"
    assert metricas.etiqueta_partido("H13-demo-P1") == "H13-demo-P1"
    assert metricas.etiqueta_partido("cualquier cosa") == "otro"
    assert metricas.etiqueta_partido("F2030-0631") == "otro"


def test_chequeo_en_segundo_plano_publica_disponibilidad():
    metricas._chequear_una("prueba", lambda: True, actualizar_corte=False)
    metricas._chequear_una("prueba_caida", lambda: (_ for _ in ()).throw(OSError()),
                           actualizar_corte=False)
    texto = cliente.get("/metrics").text
    assert re.search(r'fixture_dependencia_disponible\{fuente="prueba"\} 1\.0', texto)
    assert re.search(r'fixture_dependencia_disponible\{fuente="prueba_caida"\} 0\.0', texto)
