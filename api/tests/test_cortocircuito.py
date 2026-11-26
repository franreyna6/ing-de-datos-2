"""Pruebas del corte rapido por fuente (Hito 13, mejora transversal).

No necesitan bases levantadas: se usan funciones de prueba en lugar de los
adaptadores reales.

Ejecutar:  pytest tests/ -v
"""
import time

import pytest

from app.core import metricas
from app.core.cortocircuito import Cortocircuito
from app.core.errores import ErrorDependencia


def _funcion_que_falla(conexion=True):
    llamadas = {"n": 0}

    def f():
        llamadas["n"] += 1
        raise ErrorDependencia("prueba", "sin conexion", conexion=conexion)
    return f, llamadas


def test_una_falla_de_conexion_abre_el_corte_y_la_siguiente_no_se_intenta():
    corte = Cortocircuito("prueba_abre", ventana_s=30)
    f, llamadas = _funcion_que_falla()
    medida = metricas._medir("prueba_abre", "op", f, corte)
    with pytest.raises(ErrorDependencia):
        medida()
    assert llamadas["n"] == 1
    t0 = time.perf_counter()
    with pytest.raises(ErrorDependencia):
        medida()                                   # rechazada sin llamar a la base
    assert llamadas["n"] == 1
    assert time.perf_counter() - t0 < 0.05


def test_un_dato_invalido_no_abre_el_corte():
    corte = Cortocircuito("prueba_validacion", ventana_s=30)
    f, llamadas = _funcion_que_falla(conexion=False)
    medida = metricas._medir("prueba_validacion", "op", f, corte)
    for _ in range(3):
        with pytest.raises(ErrorDependencia):
            medida()
    assert llamadas["n"] == 3                      # todas se intentaron
    assert corte.permitir()


def test_al_vencer_la_ventana_pasa_una_sola_prueba():
    corte = Cortocircuito("prueba_semiabierto", ventana_s=0.2)
    corte.registrar_falla()
    assert not corte.permitir()
    time.sleep(0.25)
    assert corte.permitir()                        # la prueba
    assert not corte.permitir()                    # las demas siguen afuera
    corte.registrar_exito()
    assert corte.permitir()                        # cerrado de nuevo


def test_ventana_cero_desactiva_el_corte():
    corte = Cortocircuito("prueba_apagado", ventana_s=0)
    corte.registrar_falla()
    assert corte.permitir()


def test_la_cache_no_intenta_redis_con_el_corte_abierto(monkeypatch):
    from app.adapters import redis_adapter as modulo
    from app.core import cortocircuito

    corte = Cortocircuito("redis", ventana_s=30)
    monkeypatch.setitem(cortocircuito._registro, "redis", corte)
    intentos = {"n": 0}

    class ClienteCaido:
        def get(self, clave):
            intentos["n"] += 1
            raise ConnectionError("Redis no responde")

    adaptador = modulo.RedisAdapter()
    monkeypatch.setattr(adaptador, "_cli", lambda: ClienteCaido())
    assert adaptador.cache_leer("cache:x") is None     # intenta, falla y abre el corte
    assert adaptador.cache_leer("cache:x") is None     # ya no intenta
    assert intentos["n"] == 1
