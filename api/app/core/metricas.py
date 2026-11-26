"""Metricas Prometheus de la API (Hito 13, RF4).

La API expone /metrics en el formato de texto de Prometheus. Prometheus la lee
cada 15 s (modelo pull, Clase 14). Aca se definen TODAS las metricas de
aplicacion; ninguna otra capa crea metricas propias.

Que se mide y con que tipo (Clase 14, "Tipos de metricas"):

  Counter   fixture_api_requests_total{metodo,ruta,estado}
            Requests atendidas. Solo sube; con rate() da requests por segundo
            (throughput) y, filtrando estado 5xx, la tasa de errores.
  Histogram fixture_api_request_duration_seconds{metodo,ruta}
            Tiempo de respuesta medido DENTRO de la API (el mismo que el header
            X-Duracion-ms del Hito 12). Con histogram_quantile() da p50/p95/p99.
  Histogram fixture_dependencia_duration_seconds{fuente,operacion,resultado}
            Tiempo de cada llamada a una base, medido alrededor del adaptador.
            Permite separar "la API esta lenta" de "la base X esta lenta".
  Gauge     fixture_dependencia_disponible{fuente}
            1/0 segun el chequeo de protocolo de cada adaptador (el mismo de
            /salud). Lo actualiza un hilo en segundo plano, no el scrape.
  Gauge     fixture_dependencia_chequeo_seconds{fuente}
            Cuanto tardo el ultimo chequeo de esa fuente.
  Counter   fixture_cache_comentarios_total{estado}
            Lecturas de comentarios por resultado de cache: OFF | MISS | HIT.
  Counter   fixture_comentarios_creados_total{partido}
            Escrituras de comentarios en Cassandra por partido ("escrituras de
            Cassandra por partido" del dashboard de la Clase 14).
  Gauge     fixture_cortocircuito_abierto{fuente}
  Counter   fixture_cortocircuito_rechazos_total{fuente}
            Estado del corte rapido por fuente (app/core/cortocircuito.py) y
            llamadas que no se intentaron por estar abierto.

Cardinalidad controlada (para no multiplicar series):
  - 'ruta' es la PLANTILLA de la ruta (/partidos/{codigo}/comentarios), nunca
    la URL con el codigo real; las URLs que no existen se agrupan en "sin_ruta".
  - 'partido' solo toma el codigo si respeta el formato del fixture o de los
    partidos de laboratorio; cualquier otro valor se agrupa en "otro".

Integridad (RNF5 del Hito 13): medir no cambia ningun dato. Los contadores viven
en memoria del proceso; /metrics solo los lee. Se reinician al reiniciar la API
(Prometheus lo detecta y rate() lo tolera).
"""
from __future__ import annotations

import functools
import os
import re
import threading
import time

from prometheus_client import Counter, Gauge, Histogram, disable_created_metrics

from app.core.registro import logger

# Sin las series *_created (marca de creacion de cada contador): no se usan en
# ninguna consulta y duplicarian la cantidad de series expuestas.
disable_created_metrics()

# Buckets en segundos. Cubren desde 2.5 ms (lecturas cacheadas del Hito 12,
# p50 ~3 ms) hasta 10 s (mas alla del timeout de 3 s de las dependencias).
_BUCKETS = (0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

REQUESTS = Counter(
    "fixture_api_requests_total",
    "Requests HTTP atendidas por la API, por metodo, plantilla de ruta y codigo HTTP.",
    ["metodo", "ruta", "estado"],
)
DURACION = Histogram(
    "fixture_api_request_duration_seconds",
    "Tiempo de respuesta medido dentro de la API, en segundos.",
    ["metodo", "ruta"],
    buckets=_BUCKETS,
)
DEP_DURACION = Histogram(
    "fixture_dependencia_duration_seconds",
    "Duracion de cada llamada de la API a una base, medida alrededor del adaptador.",
    ["fuente", "operacion", "resultado"],
    buckets=_BUCKETS,
)
DEP_DISPONIBLE = Gauge(
    "fixture_dependencia_disponible",
    "1 si el ultimo chequeo de protocolo de la fuente respondio bien, 0 si no.",
    ["fuente"],
)
DEP_CHEQUEO = Gauge(
    "fixture_dependencia_chequeo_seconds",
    "Duracion del ultimo chequeo de disponibilidad de la fuente, en segundos.",
    ["fuente"],
)
CACHE = Counter(
    "fixture_cache_comentarios_total",
    "Lecturas de comentarios segun el resultado de la cache de Redis (OFF, MISS, HIT).",
    ["estado"],
)
COMENTARIOS_CREADOS = Counter(
    "fixture_comentarios_creados_total",
    "Comentarios escritos en Cassandra a traves de la API, por partido.",
    ["partido"],
)

CORTE_ABIERTO = Gauge(
    "fixture_cortocircuito_abierto",
    "1 si el corte rapido de la fuente esta abierto (fallo reciente), 0 si esta cerrado.",
    ["fuente"],
)
CORTE_RECHAZOS = Counter(
    "fixture_cortocircuito_rechazos_total",
    "Llamadas que no se intentaron porque el corte rapido de la fuente estaba abierto.",
    ["fuente"],
)

# Codigos validos para la etiqueta 'partido': fixture real (F2030-001) o
# partidos de laboratorio de las pruebas de carga (H12-..., H13-...).
_PARTIDO_VALIDO = re.compile(r"^(F2030-\d{3}|H1[23]-[A-Za-z0-9_-]{1,40})$")


def etiqueta_partido(codigo: str) -> str:
    return codigo if _PARTIDO_VALIDO.match(codigo or "") else "otro"


# --------------------------------------------------------------------------
# Instrumentacion de los adaptadores
# --------------------------------------------------------------------------
def _medir(fuente: str, operacion: str, funcion, corte=None):
    """Mide la llamada y, si hay corte rapido, lo aplica (Hito 13).

    resultado = ok | error | cortocircuito (no se intento: la fuente fallo hace poco).
    """
    from app.core.errores import ErrorDependencia

    @functools.wraps(funcion)
    def envoltura(*args, **kwargs):
        t0 = time.perf_counter()
        resultado = "ok"
        try:
            if corte is not None and not corte.permitir():
                resultado = "cortocircuito"
                raise ErrorDependencia(fuente, "corte rapido abierto: la fuente fallo hace poco")
            respuesta = funcion(*args, **kwargs)
            if corte is not None:
                corte.registrar_exito()
            return respuesta
        except ErrorDependencia as e:
            if resultado != "cortocircuito":
                resultado = "error"
                if corte is not None and getattr(e, "conexion", True):
                    corte.registrar_falla()
            raise
        except Exception:
            resultado = "error"
            raise
        finally:
            DEP_DURACION.labels(fuente, operacion, resultado).observe(time.perf_counter() - t0)
    return envoltura


def instrumentar_adaptador(adaptador, fuente: str, operaciones: list[str],
                           sin_corte: tuple[str, ...] = ()) -> None:
    """Envuelve los metodos publicos del adaptador para medir su duracion.

    No modifica el codigo de los adaptadores: reemplaza el atributo en la
    instancia. Los servicios llaman a 'adaptador.metodo(...)', asi que pasan
    por la envoltura sin enterarse. Las operaciones de 'sin_corte' se miden
    pero manejan el corte rapido por su cuenta (la cache de Redis).
    """
    from app.core import cortocircuito
    for op in operaciones:
        original = getattr(adaptador, op)
        if getattr(original, "_fixture_medido", False):
            continue  # ya instrumentado (p. ej. recarga del modulo)
        corte = None if op in sin_corte else cortocircuito.de(fuente)
        medido = _medir(fuente, op, original, corte)
        medido._fixture_medido = True
        setattr(adaptador, op, medido)


# --------------------------------------------------------------------------
# Disponibilidad en segundo plano
# --------------------------------------------------------------------------
def _chequear_una(fuente: str, verificar, actualizar_corte: bool = True) -> None:
    t0 = time.perf_counter()
    try:
        ok = bool(verificar())
    except Exception:
        ok = False
    DEP_CHEQUEO.labels(fuente).set(time.perf_counter() - t0)
    DEP_DISPONIBLE.labels(fuente).set(1 if ok else 0)
    if actualizar_corte:
        # El chequeo tambien abre o cierra el corte rapido: si la base volvio,
        # la API la usa de nuevo sin esperar a que una request lo descubra.
        from app.core import cortocircuito
        corte = cortocircuito.de(fuente)
        corte.registrar_exito() if ok else corte.registrar_falla()


def iniciar_chequeo_de_dependencias(chequeos: dict) -> threading.Thread | None:
    """Arranca un hilo que chequea cada fuente cada METRICAS_INTERVALO_S segundos.

    Por que en segundo plano y no al momento del scrape: /salud chequea las 6
    fuentes en serie y, con bases caidas, puede tardar varios segundos (timeout
    de 3 s por fuente). Si el scrape esperara eso, Prometheus marcaria a la API
    como caida justo cuando mas hace falta medirla. Con el hilo, /metrics
    responde siempre al instante con el ultimo estado conocido.

    METRICAS_INTERVALO_S=0 lo desactiva (tests).
    """
    intervalo = float(os.environ.get("METRICAS_INTERVALO_S", "15"))
    if intervalo <= 0:
        return None

    def bucle():
        while True:
            for fuente, verificar in chequeos.items():
                _chequear_una(fuente, verificar)
            time.sleep(intervalo)

    hilo = threading.Thread(target=bucle, name="chequeo-dependencias", daemon=True)
    hilo.start()
    logger.info("chequeo de dependencias en segundo plano cada %.0f s", intervalo)
    return hilo
