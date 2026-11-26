"""Corte rapido (circuit breaker) por fuente — mejora transversal del Hito 13.

Problema observado con el monitoreo (Hito 13, corrida 20261126-040222):
cuando una base esta caida, en Windows cada intento de conexion tarda unos
2,4 s en fallar. La API lo pagaba en CADA request: con Redis detenido, la
lectura de comentarios paso de un p95 de unos 10 ms a mas de 4,8 s y el
throughput de la API cayo de unos 54 a 9 requests/s, aunque Cassandra estaba
sana y la respuesta era correcta.

Solucion: despues de una falla de CONEXION, la fuente queda "abierta" durante
CORTOCIRCUITO_S segundos (10 por defecto). Mientras esta abierta:
  - las rutas que dependen de esa base responden 503 al instante, sin esperar
    el timeout;
  - la cache de comentarios ni siquiera intenta hablar con Redis y lee
    Cassandra directamente.
Al vencer la ventana pasa UNA sola request de prueba (semiabierto): si
funciona, se cierra; si falla, se vuelve a abrir. El chequeo en segundo plano
de app/core/metricas.py tambien lo abre o lo cierra cada 15 s.

Solo cuentan las fallas de conexion (ErrorDependencia con conexion=True).
Un parametro invalido no abre el corte: si lo hiciera, un cliente con un
pedido mal formado podria dejar sin servicio a todos los demas.

CORTOCIRCUITO_S=0 lo desactiva (comportamiento del Hito 12, para comparar).
"""
from __future__ import annotations

import os
import threading
import time

from app.core.metricas import CORTE_ABIERTO, CORTE_RECHAZOS


class Cortocircuito:
    def __init__(self, fuente: str, ventana_s: float) -> None:
        self.fuente = fuente
        self.ventana_s = ventana_s
        self._abierto_hasta = 0.0      # 0 = cerrado
        self._lock = threading.Lock()
        CORTE_ABIERTO.labels(fuente).set(0)

    @property
    def activo(self) -> bool:
        return self.ventana_s > 0

    def permitir(self) -> bool:
        """True si la llamada puede intentar usar la fuente."""
        if not self.activo:
            return True
        with self._lock:
            if self._abierto_hasta == 0.0:
                return True
            ahora = time.monotonic()
            if ahora < self._abierto_hasta:
                CORTE_RECHAZOS.labels(self.fuente).inc()
                return False
            # Semiabierto: deja pasar esta llamada como prueba y mantiene a las
            # demas afuera durante otra ventana, hasta saber si la fuente volvio.
            self._abierto_hasta = ahora + self.ventana_s
            return True

    def registrar_falla(self) -> None:
        if not self.activo:
            return
        with self._lock:
            self._abierto_hasta = time.monotonic() + self.ventana_s
        CORTE_ABIERTO.labels(self.fuente).set(1)

    def registrar_exito(self) -> None:
        if not self.activo:
            return
        with self._lock:
            cambio = self._abierto_hasta != 0.0
            self._abierto_hasta = 0.0
        if cambio:
            CORTE_ABIERTO.labels(self.fuente).set(0)


_registro: dict[str, Cortocircuito] = {}
_lock_registro = threading.Lock()


def de(fuente: str) -> Cortocircuito:
    """Corte de una fuente (uno por base, compartido por toda la API)."""
    with _lock_registro:
        if fuente not in _registro:
            _registro[fuente] = Cortocircuito(fuente, float(os.environ.get("CORTOCIRCUITO_S", "10")))
        return _registro[fuente]
