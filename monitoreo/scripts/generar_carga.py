"""Generador de carga mixta del Hito 13 (usuarios virtuales contra la API).

Objetivo: tener trafico real mientras Prometheus mide, para que el tablero
muestre latencia, throughput y errores de las 6 bases a la vez (Clase 14:
"evidencia de monitoreo durante una prueba de carga").

Diferencia con el Hito 12: el Hito 12 media una sola ruta (comentarios) para
comparar linea base contra optimizacion. Aca la mezcla recorre TODAS las bases,
porque lo que se quiere observar es el comportamiento transversal.

Modelo (igual que el Hito 12): usuarios virtuales en lazo cerrado. Cada uno
elige una operacion segun los pesos, la ejecuta, espera una pausa al azar y
repite. Todas las requests pasan por la API; nunca se va directo a una base.

Integridad (RNF5): las escrituras van a partidos de LABORATORIO propios de la
corrida ('H13-<etiqueta>-P1'...), que no existen en el fixture real. Las
lecturas usan datos de muestra de los hitos anteriores, sin modificarlos.

Uso suelto (normalmente lo llama ejecutar_prueba_controlada.py):
  python scripts/generar_carga.py --usuarios 20 --duracion 120
"""
from __future__ import annotations

import argparse
import collections
import csv
import gzip
import http.client
import json
import random
import threading
import time
import urllib.parse
from pathlib import Path

# Datos de muestra que ya devuelven 200 (los mismos del Hito 11, prueba_api.py).
EQUIPO = "ARG"
PARTIDO_EVENTOS = "F2030-001"
PARTIDO_DETALLE = "F2030-001"
PARTIDO_INFLUX = "F2030-018"
INFLUX_DESDE, INFLUX_HASTA = "2030-06-13T08:00:00Z", "2030-06-13T08:05:00Z"
SESION = "S0001"

# (nombre, fuente, peso). Los pesos suman 1.0. Comentarios concentran la carga,
# como despues de un gol (Hito 12); el resto mantiene vivas las otras bases.
MEZCLA = [
    ("leer_comentarios", "cassandra+redis", 0.40),
    ("escribir_comentario", "cassandra", 0.15),
    ("equipo", "mongodb", 0.10),
    ("jugadores", "mongodb", 0.05),
    ("eventos", "neo4j", 0.10),
    ("estadisticas", "influxdb", 0.08),
    ("detalle", "iris", 0.07),
    ("sesion", "redis", 0.05),
]


def partidos_de_laboratorio(etiqueta: str) -> dict[str, str]:
    return {"P1": f"H13-{etiqueta}-P1", "P2": f"H13-{etiqueta}-P2"}


class ClienteHTTP:
    """Una conexion persistente por usuario virtual (como un navegador)."""

    def __init__(self, url_base: str, timeout_s: float):
        u = urllib.parse.urlparse(url_base)
        self.host, self.port, self.timeout = u.hostname, u.port or 80, timeout_s
        self.conn = None

    def request(self, metodo: str, ruta: str, cuerpo: dict | None = None):
        if self.conn is None:
            self.conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        cab = {"Content-Type": "application/json"} if datos else {}
        t0 = time.perf_counter()
        try:
            self.conn.request(metodo, ruta, body=datos, headers=cab)
            r = self.conn.getresponse()
            crudo = r.read()
            lat = (time.perf_counter() - t0) * 1000
            return r.status, r.getheader("X-Cache", ""), r.getheader("X-Duracion-ms", ""), crudo, lat, ""
        except Exception as e:  # sin conexion, timeout, reset
            lat = (time.perf_counter() - t0) * 1000
            try:
                self.conn.close()
            finally:
                self.conn = None
            return 0, "", "", b"", lat, type(e).__name__


class GeneradorCarga:
    def __init__(self, url: str, usuarios: int, etiqueta: str, semilla: int = 2030,
                 pausa=(0.10, 0.30), timeout_s: float = 10.0):
        self.url, self.usuarios, self.etiqueta = url, usuarios, etiqueta
        self.pausa, self.timeout_s = pausa, timeout_s
        self.partidos = partidos_de_laboratorio(etiqueta)
        self._rnd_base = random.Random(semilla)
        self._detener = threading.Event()
        self._hilos: list[threading.Thread] = []
        self._lock = threading.Lock()
        self.registros: list[tuple] = []        # (t_epoch, op, fuente, status, lat_ms, x_cache, x_dur, error)
        self.ventanas_escritas: set[tuple[str, str]] = set()
        self.inicio = self.fin = None

    def _operacion(self, rnd: random.Random, cli: ClienteHTTP, n: int):
        op, fuente, _ = rnd.choices(MEZCLA, weights=[m[2] for m in MEZCLA])[0]
        partido = self.partidos["P1"] if rnd.random() < 0.8 else self.partidos["P2"]
        if op == "leer_comentarios":
            return op, fuente, cli.request("GET", f"/partidos/{partido}/comentarios?limit=20")
        if op == "escribir_comentario":
            cuerpo = {"usuarioId": f"h13-u{rnd.randint(1, 5000):04d}",
                      "contenido": f"Comentario de carga H13 {self.etiqueta} #{n}"}
            res = cli.request("POST", f"/partidos/{partido}/comentarios", cuerpo)
            if res[0] == 201:
                try:
                    v = json.loads(res[3]).get("ventana")
                    if v:
                        with self._lock:
                            self.ventanas_escritas.add((partido, v))
                except ValueError:
                    pass
            return op, fuente, res
        if op == "equipo":
            return op, fuente, cli.request("GET", f"/equipos/{EQUIPO}")
        if op == "jugadores":
            return op, fuente, cli.request("GET", f"/equipos/{EQUIPO}/jugadores?limit=10")
        if op == "eventos":
            return op, fuente, cli.request("GET", f"/partidos/{PARTIDO_EVENTOS}/eventos?limit=10")
        if op == "estadisticas":
            q = urllib.parse.urlencode({"desde": INFLUX_DESDE, "hasta": INFLUX_HASTA})
            return op, fuente, cli.request("GET", f"/partidos/{PARTIDO_INFLUX}/estadisticas?{q}")
        if op == "detalle":
            return op, fuente, cli.request("GET", f"/partidos/{PARTIDO_DETALLE}/detalle")
        return op, fuente, cli.request("GET", f"/sesiones/{SESION}")

    def _usuario(self, indice: int):
        rnd = random.Random(self._rnd_base.random() + indice)
        cli = ClienteHTTP(self.url, self.timeout_s)
        n = 0
        while not self._detener.is_set():
            n += 1
            t = time.time()
            op, fuente, (st, xc, xd, _crudo, lat, err) = self._operacion(rnd, cli, n)
            with self._lock:
                self.registros.append((t, op, fuente, st, round(lat, 2), xc, xd, err))
            self._detener.wait(rnd.uniform(*self.pausa))

    def iniciar(self):
        self.inicio = time.time()
        for i in range(self.usuarios):
            h = threading.Thread(target=self._usuario, args=(i,), daemon=True, name=f"vu-{i}")
            h.start()
            self._hilos.append(h)
            time.sleep(0.05)   # rampa corta para no abrir todas las conexiones a la vez

    def detener(self):
        self._detener.set()
        for h in self._hilos:
            h.join(timeout=self.timeout_s + 2)
        self.fin = time.time()

    def guardar_csv(self, ruta: Path):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(ruta, "wt", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t_epoch", "operacion", "fuente", "http", "latencia_cliente_ms",
                        "x_cache", "x_duracion_api_ms", "error_cliente"])
            with self._lock:
                w.writerows(self.registros)


def percentil(valores: list[float], p: float) -> float | None:
    if not valores:
        return None
    v = sorted(valores)
    k = (len(v) - 1) * p
    i, f = int(k), k - int(k)
    return round(v[i] + (v[min(i + 1, len(v) - 1)] - v[i]) * f, 2)


def resumir(registros: list[tuple], desde: float, hasta: float) -> dict:
    """Resumen del lado del cliente para una ventana de tiempo."""
    sel = [r for r in registros if desde <= r[0] < hasta]
    dur = max(hasta - desde, 1e-9)
    lat = [r[4] for r in sel]
    por_op = collections.defaultdict(list)
    for r in sel:
        por_op[r[1]].append(r)
    cache = collections.Counter(r[5] for r in sel if r[1] == "leer_comentarios")
    return {
        "requests": len(sel),
        "requests_por_segundo": round(len(sel) / dur, 1),
        "errores_5xx": sum(1 for r in sel if 500 <= r[3] < 600),
        "errores_conexion_cliente": sum(1 for r in sel if r[3] == 0),
        "respuestas_4xx": sum(1 for r in sel if 400 <= r[3] < 500),
        "tasa_error": round(sum(1 for r in sel if r[3] == 0 or r[3] >= 500) / len(sel), 4) if sel else None,
        "latencia_cliente_ms": {"p50": percentil(lat, .50), "p95": percentil(lat, .95),
                                "p99": percentil(lat, .99), "max": max(lat) if lat else None},
        "cache_lecturas_comentarios": dict(cache),
        "por_operacion": {
            op: {"requests": len(rs),
                 "p95_ms": percentil([x[4] for x in rs], .95),
                 "codigos": dict(collections.Counter(x[3] for x in rs))}
            for op, rs in sorted(por_op.items())},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--usuarios", type=int, default=20)
    ap.add_argument("--duracion", type=int, default=120, help="segundos")
    ap.add_argument("--etiqueta", default=time.strftime("%Y%m%d-%H%M%S", time.gmtime()))
    a = ap.parse_args()
    g = GeneradorCarga(a.url, a.usuarios, a.etiqueta)
    print(f"Carga: {a.usuarios} usuarios durante {a.duracion} s contra {a.url}")
    g.iniciar()
    time.sleep(a.duracion)
    g.detener()
    print(json.dumps(resumir(g.registros, g.inicio, g.fin), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
