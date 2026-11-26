"""Prueba de falla controlada bajo carga, observada con Prometheus y Grafana (RF10).

Dos experimentos sobre contenedores de LABORATORIO (RNF11: nunca se borran
volumenes; solo se detiene y se vuelve a iniciar un contenedor):

A) Caida de Redis durante una prueba de carga (degradacion parcial).
   Tres fases de igual duracion con la misma carga mixta (generar_carga.py):
     1. normal        todas las bases arriba
     2. falla         docker stop fixture2030-redis
     3. recuperacion  docker start fixture2030-redis
   Pregunta: si se cae la cache, ¿se cae el Fixture o solo se degrada? La API
   del Hito 12 lee comentarios de Redis y, si no puede, va a Cassandra.

B) Caida de Cassandra sin carga (alerta critica, "Cassandra Node Down").
   docker stop fixture2030-cassandra hasta que la alerta BaseNoDisponible pase
   a firing; se comprueba que comentarios responde 503 y que las rutas de otras
   bases siguen en 200 (aislamiento); docker start y se mide la recuperacion.

Todo lo que se informa sale de lo medido: series de Prometheus (paso de 15 s),
alertas (serie ALERTS), registros del lado del cliente y capturas de Grafana
con el rango exacto de la prueba.

Evidencia: monitoreo/evidencia/prueba_de_falla/<etiqueta>/
  resumen.md                       informe legible (lo que se cita en docs/)
  metadata.json                    parametros, horarios, commit
  series_prometheus.csv            series clave, una fila cada 15 s
  serie_cliente_5s.csv             throughput, p95 y errores del cliente cada 5 s
  alertas.json                     intervalos pending/firing de cada alerta
  alertmanager_*.json              alertas recibidas por Alertmanager durante la falla
  experimento_b_cassandra.json     respuestas de la API con Cassandra caida
  requests_cliente.csv.gz          una fila por request
  ../dashboards/prueba_<etiqueta>_*.png  capturas del tablero

Uso:
  python scripts/ejecutar_prueba_controlada.py                      # A + B, fases de 150 s
  python scripts/ejecutar_prueba_controlada.py --fase 90 --sin-cassandra
Requisitos: bases, API (con CACHE_COMENTARIOS_TTL_S > 0) y monitoreo levantados.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import threading
import time
import urllib.parse

import capturar_dashboard
from generar_carga import GeneradorCarga, partidos_de_laboratorio, resumir, percentil
from lib_monitoreo import (ALERTMANAGER, API, CONTENEDORES, DIR_EVIDENCIA, PROMETHEUS, anotar,
                           aviso, contenedor_corriendo, docker, escribir_json, escribir_texto,
                           etiqueta_nueva, http, http_json, info, info_git, iso, paso,
                           prom_consulta, prom_rango, prom_valor)

PASO_S = 15

SERIES = {
    "rps_api": "sum(rate(fixture_api_requests_total[1m]))",
    "p50_api_s": "histogram_quantile(0.50, sum by (le) (rate(fixture_api_request_duration_seconds_bucket[1m])))",
    "p95_api_s": "histogram_quantile(0.95, sum by (le) (rate(fixture_api_request_duration_seconds_bucket[1m])))",
    "p99_api_s": "histogram_quantile(0.99, sum by (le) (rate(fixture_api_request_duration_seconds_bucket[1m])))",
    "tasa_5xx": '(sum(rate(fixture_api_requests_total{estado=~"5.."}[1m])) or vector(0)) / sum(rate(fixture_api_requests_total[1m]))',
    "aciertos_cache": 'sum(rate(fixture_cache_comentarios_total{estado="HIT"}[1m])) / sum(rate(fixture_cache_comentarios_total{estado=~"HIT|MISS"}[1m]))',
    "p95_comentarios_s": 'histogram_quantile(0.95, sum by (le) (rate(fixture_api_request_duration_seconds_bucket{ruta="/partidos/{codigo}/comentarios",metodo="GET"}[1m])))',
    "p95_dep_redis_s": 'histogram_quantile(0.95, sum by (le) (rate(fixture_dependencia_duration_seconds_bucket{fuente="redis"}[1m])))',
    "p95_dep_cassandra_s": 'histogram_quantile(0.95, sum by (le) (rate(fixture_dependencia_duration_seconds_bucket{fuente="cassandra"}[1m])))',
    "lecturas_cassandra_por_s": 'sum(rate(fixture_dependencia_duration_seconds_count{fuente="cassandra",operacion="leer_comentarios"}[1m]))',
    "redis_up_exporter": "max(redis_up)",
    "redis_sonda": 'max(probe_success{componente="redis"})',
    "redis_disponible_api": 'max(fixture_dependencia_disponible{fuente="redis"})',
    "cassandra_disponible_api": 'max(fixture_dependencia_disponible{fuente="cassandra"})',
    "cassandra_sonda_tcp": 'max(probe_success{componente="cassandra"})',
    "alertas_firing": 'count(ALERTS{alertstate="firing"}) or vector(0)',
    "corte_redis_abierto": 'max(fixture_cortocircuito_abierto{fuente="redis"})',
    "rechazos_corte_redis_por_s": 'sum(rate(fixture_cortocircuito_rechazos_total{fuente="redis"}[1m]))',
}

FASES = ("normal", "falla", "recuperacion")


# --------------------------------------------------------------------------
# Ayudas de analisis
# --------------------------------------------------------------------------
def series_en_rango(inicio: float, fin: float) -> tuple[list[float], dict[str, dict[float, float]]]:
    tiempos: set[float] = set()
    datos: dict[str, dict[float, float]] = {}
    for nombre, expr in SERIES.items():
        res = prom_rango(expr, inicio, fin, PASO_S)
        valores = {}
        if res:
            for t, v in res[0]["values"]:
                try:
                    f = float(v)
                except ValueError:
                    continue
                if f == f:  # descarta NaN (sin trafico en la ventana)
                    valores[float(t)] = f
                    tiempos.add(float(t))
        datos[nombre] = valores
    return sorted(tiempos), datos


def fase_de(t: float, marcas: dict) -> str:
    if t < marcas["inicio"]:
        return "antes"
    if t < marcas["falla"]:
        return "normal"
    if t < marcas["recuperacion"]:
        return "falla"
    if t <= marcas["fin"]:
        return "recuperacion"
    return "despues"


def estadistica_por_fase(datos: dict, marcas: dict, asentamiento: float = 60) -> dict:
    """Promedio y maximo de cada serie dentro de cada fase.

    Se descartan los primeros 'asentamiento' segundos de cada fase: las
    consultas usan rate(...[1m]), asi que el primer minuto mezcla la fase
    anterior con la actual.
    """
    limites = {"normal": (marcas["inicio"], marcas["falla"]),
               "falla": (marcas["falla"], marcas["recuperacion"]),
               "recuperacion": (marcas["recuperacion"], marcas["fin"])}
    out = {}
    for fase, (a, b) in limites.items():
        out[fase] = {}
        for nombre, valores in datos.items():
            sel = [v for t, v in valores.items() if a + asentamiento <= t <= b]
            out[fase][nombre] = ({"promedio": round(statistics.fmean(sel), 4), "max": round(max(sel), 4),
                                  "muestras": len(sel)} if sel else None)
    return out


def primer_cambio(valores: dict[float, float], desde: float, condicion) -> float | None:
    for t in sorted(valores):
        if t >= desde and condicion(valores[t]):
            return t
    return None


def intervalos_de_alertas(inicio: float, fin: float) -> list[dict]:
    """Intervalos pending/firing de cada alerta a partir de la serie ALERTS."""
    out = []
    for estado in ("pending", "firing"):
        for r in prom_rango(f'ALERTS{{alertstate="{estado}"}}', inicio, fin, PASO_S):
            m = r["metric"]
            ts = [float(t) for t, _ in r["values"]]
            if not ts:
                continue
            tramos, a, prev = [], ts[0], ts[0]
            for t in ts[1:]:
                if t - prev > PASO_S * 1.5:
                    tramos.append((a, prev))
                    a = t
                prev = t
            tramos.append((a, prev))
            for a, b in tramos:
                out.append({"alerta": m.get("alertname"), "estado": estado,
                            "componente": m.get("componente", m.get("fuente", "")),
                            "origen": m.get("job", ""),
                            "severidad": m.get("severidad", ""), "desde": a, "hasta": b,
                            "desde_utc": iso(a), "hasta_utc": iso(b)})
    return sorted(out, key=lambda x: (x["desde"], x["alerta"]))


def alertmanager_snapshot() -> list[dict]:
    st, js = http_json("GET", f"{ALERTMANAGER}/api/v2/alerts", timeout=10)
    if st != 200 or not isinstance(js, list):
        return []
    return [{"alerta": a["labels"].get("alertname"), "labels": a["labels"],
             "estado": a.get("status", {}).get("state"), "desde": a.get("startsAt"),
             "resumen": a.get("annotations", {}).get("resumen", "")} for a in js]


def serie_cliente(registros: list[tuple], inicio: float, fin: float, ancho: float = 5.0) -> list[dict]:
    filas, t = [], inicio
    while t < fin:
        sel = [r for r in registros if t <= r[0] < t + ancho]
        lat = [r[4] for r in sel]
        filas.append({"segundo": round(t - inicio), "requests_por_s": round(len(sel) / ancho, 1),
                      "p50_ms": percentil(lat, .5), "p95_ms": percentil(lat, .95),
                      "errores_5xx_o_conexion": sum(1 for r in sel if r[3] == 0 or r[3] >= 500),
                      "lecturas_comentarios_hit": sum(1 for r in sel if r[1] == "leer_comentarios" and r[5] == "HIT"),
                      "lecturas_comentarios_miss": sum(1 for r in sel if r[1] == "leer_comentarios" and r[5] == "MISS")})
        t += ancho
    return filas


def esperar_hasta(momento: float):
    while True:
        resta = momento - time.time()
        if resta <= 0:
            return
        time.sleep(min(resta, 5))


# --------------------------------------------------------------------------
# Experimento A
# --------------------------------------------------------------------------
def verificar_cache(etiqueta: str) -> list[str]:
    """Dos lecturas seguidas del mismo partido: con cache encendida, MISS y luego HIT."""
    p = partidos_de_laboratorio(etiqueta)["P1"]
    estados = []
    for _ in range(2):
        st, h, _ = http("GET", f"{API}/partidos/{p}/comentarios?limit=20", timeout=10)
        estados.append(h.get("X-Cache", h.get("x-cache", f"HTTP {st}")))
    return estados


def experimento_a(a, etiqueta: str, dir_salida, meta: dict) -> dict:
    contenedor = CONTENEDORES["redis"]
    paso(f"Experimento A: caida de Redis bajo carga ({a.usuarios} usuarios, 3 fases de {a.fase} s)")
    gen = GeneradorCarga(API, a.usuarios, etiqueta)
    muestras: list[dict] = []
    fin_muestreo = threading.Event()

    def muestrear():
        while not fin_muestreo.is_set():
            muestras.append({"t": time.time(), "p95_api_s": prom_valor(SERIES["p95_api_s"]),
                             "redis_up": prom_valor(SERIES["redis_up_exporter"]),
                             "alertas_firing": prom_valor(SERIES["alertas_firing"])})
            fin_muestreo.wait(PASO_S)

    hilo = threading.Thread(target=muestrear, daemon=True)
    marcas = {"inicio": time.time()}
    gen.iniciar()
    hilo.start()
    anotar(f"H13 {etiqueta}: inicio de la carga (fase normal)", ["hito13", "carga"], marcas["inicio"])
    info(f"Fase normal hasta {iso(marcas['inicio'] + a.fase)}")

    esperar_hasta(marcas["inicio"] + a.fase)
    marcas["falla"] = time.time()
    anotar(f"H13 {etiqueta}: FALLA controlada - docker stop {contenedor}", ["hito13", "falla", "redis"], marcas["falla"])
    r = docker("stop", contenedor, timeout=120)
    info(f"docker stop {contenedor}: {'ok' if r.returncode == 0 else r.stderr.strip()[:200]}")
    meta["docker_stop_redis_s"] = round(time.time() - marcas["falla"], 1)

    # Lo que ve Alertmanager hacia el final de la falla (si la alerta llego a dispararse).
    esperar_hasta(marcas["falla"] + a.fase - 10)
    am_falla = alertmanager_snapshot()

    esperar_hasta(marcas["falla"] + a.fase)
    marcas["recuperacion"] = time.time()
    r = docker("start", contenedor, timeout=120)
    anotar(f"H13 {etiqueta}: RECUPERACION - docker start {contenedor}", ["hito13", "recuperacion", "redis"],
           marcas["recuperacion"])
    info(f"docker start {contenedor}: {'ok' if r.returncode == 0 else r.stderr.strip()[:200]}")

    esperar_hasta(marcas["recuperacion"] + a.fase)
    gen.detener()
    marcas["fin"] = gen.fin
    anotar(f"H13 {etiqueta}: fin de la carga", ["hito13", "carga"], marcas["fin"])
    info("Esperando 45 s mas para que Prometheus registre el final y resuelva las alertas...")
    time.sleep(45)
    fin_muestreo.set()

    # ----- analisis -----
    paso("Analizando el experimento A con los datos de Prometheus")
    ini_rango, fin_rango = marcas["inicio"] - 60, marcas["fin"] + 45
    tiempos, datos = series_en_rango(ini_rango, fin_rango)
    with open(dir_salida / "series_prometheus.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tiempo_utc", "segundos_desde_inicio", "fase", *SERIES.keys()])
        for t in tiempos:
            w.writerow([iso(t), round(t - marcas["inicio"]), fase_de(t, marcas),
                        *[("" if datos[n].get(t) is None else round(datos[n][t], 6)) for n in SERIES]])

    cliente = {f: resumir(gen.registros, x, y) for f, (x, y) in {
        "normal": (marcas["inicio"], marcas["falla"]),
        "falla": (marcas["falla"], marcas["recuperacion"]),
        "recuperacion": (marcas["recuperacion"], marcas["fin"])}.items()}
    cliente["total"] = resumir(gen.registros, marcas["inicio"], marcas["fin"])
    gen.guardar_csv(dir_salida / "requests_cliente.csv.gz")
    filas5 = serie_cliente(gen.registros, marcas["inicio"], marcas["fin"])
    with open(dir_salida / "serie_cliente_5s.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas5[0].keys()))
        w.writeheader()
        w.writerows(filas5)

    alertas = intervalos_de_alertas(ini_rango, fin_rango)
    linea_tiempo = {
        "redis_up_exporter_en_0": primer_cambio(datos["redis_up_exporter"], marcas["falla"], lambda v: v == 0),
        "redis_disponible_api_en_0": primer_cambio(datos["redis_disponible_api"], marcas["falla"], lambda v: v == 0),
        "redis_up_exporter_en_1": primer_cambio(datos["redis_up_exporter"], marcas["recuperacion"], lambda v: v == 1),
        "redis_disponible_api_en_1": primer_cambio(datos["redis_disponible_api"], marcas["recuperacion"], lambda v: v == 1),
        "aciertos_cache_bajo_0_8": primer_cambio(datos["aciertos_cache"], marcas["falla"], lambda v: v < 0.8),
        "aciertos_cache_vuelve_0_8": primer_cambio(datos["aciertos_cache"], marcas["recuperacion"], lambda v: v >= 0.8),
    }
    for al in alertas:
        if al["estado"] == "firing" and al["desde"] >= marcas["falla"]:
            clave = f"alerta_{al['alerta']}_{al['componente'] or 'global'}_firing"
            linea_tiempo.setdefault(clave, al["desde"])
    return {"marcas": marcas, "cliente": cliente, "prometheus_por_fase": estadistica_por_fase(datos, marcas),
            "linea_de_tiempo": linea_tiempo, "alertas": alertas, "alertmanager_durante_falla": am_falla,
            "ventanas_escritas": sorted(gen.ventanas_escritas), "rango": (ini_rango, fin_rango),
            "muestras_en_vivo": muestras}


# --------------------------------------------------------------------------
# Experimento B
# --------------------------------------------------------------------------
def probar_rutas() -> list[dict]:
    casos = [("cassandra", "/partidos/F2030-063/comentarios?instante=2030-06-22T20:03:00Z&limit=5"),
             ("mongodb", "/equipos/ARG"),
             ("neo4j", "/partidos/F2030-001/eventos?limit=5"),
             ("iris", "/partidos/F2030-001/detalle"),
             ("redis", "/sesiones/S0001")]
    out = []
    for fuente, ruta in casos:
        t0 = time.perf_counter()
        st, h, cuerpo = http("GET", f"{API}{ruta}", timeout=15)
        codigo = ""
        try:
            codigo = json.loads(cuerpo).get("error", {}).get("code", "") if st >= 400 else ""
        except (ValueError, AttributeError):
            pass
        out.append({"fuente": fuente, "ruta": ruta.split("?")[0], "http": st, "codigo_error": codigo,
                    "request_id": h.get("X-Request-ID", h.get("x-request-id", "")),
                    "latencia_ms": round((time.perf_counter() - t0) * 1000, 1)})
    return out


def experimento_b(etiqueta: str) -> dict:
    contenedor = CONTENEDORES["cassandra"]
    paso("Experimento B: caida de Cassandra sin carga (alerta critica)")
    m = {"inicio": time.time()}
    antes = probar_rutas()
    anotar(f"H13 {etiqueta}: FALLA B - docker stop {contenedor}", ["hito13", "falla", "cassandra"], m["inicio"])
    r = docker("stop", contenedor, timeout=180)
    info(f"docker stop {contenedor}: {'ok' if r.returncode == 0 else r.stderr.strip()[:200]}")
    m["detenido"] = time.time()

    expr_alerta = 'ALERTS{alertname="BaseNoDisponible",fuente="cassandra",alertstate="firing"}'
    m["api_ve_caida"] = m["alerta_firing"] = None
    limite = time.time() + 240
    while time.time() < limite and m["alerta_firing"] is None:
        if m["api_ve_caida"] is None and prom_valor('max(fixture_dependencia_disponible{fuente="cassandra"})') == 0:
            m["api_ve_caida"] = time.time()
        if prom_valor(f"count({expr_alerta})"):
            m["alerta_firing"] = time.time()
        time.sleep(5)
    info(f"Alerta BaseNoDisponible(cassandra): "
         f"{'firing a los %.0f s' % (m['alerta_firing'] - m['detenido']) if m['alerta_firing'] else 'no llego a firing en 240 s'}")
    durante = probar_rutas()
    am = alertmanager_snapshot()

    m["inicio_recuperacion"] = time.time()
    r = docker("start", contenedor, timeout=180)
    anotar(f"H13 {etiqueta}: RECUPERACION B - docker start {contenedor}", ["hito13", "recuperacion", "cassandra"],
           m["inicio_recuperacion"])
    info(f"docker start {contenedor}: {'ok' if r.returncode == 0 else r.stderr.strip()[:200]}")
    m["api_ve_disponible"] = m["comentarios_200"] = None
    limite = time.time() + 360
    while time.time() < limite and (m["api_ve_disponible"] is None or m["comentarios_200"] is None):
        if m["api_ve_disponible"] is None and prom_valor('max(fixture_dependencia_disponible{fuente="cassandra"})') == 1:
            m["api_ve_disponible"] = time.time()
        if m["comentarios_200"] is None:
            st, _, _ = http("GET", f"{API}/partidos/F2030-063/comentarios?instante=2030-06-22T20:03:00Z&limit=5", timeout=15)
            if st == 200:
                m["comentarios_200"] = time.time()
        time.sleep(5)
    time.sleep(40)  # que la alerta se resuelva y quede registrado
    despues = probar_rutas()
    m["fin"] = time.time()
    anotar(f"H13 {etiqueta}: fin del experimento B", ["hito13", "cassandra"], m["fin"])
    alertas = intervalos_de_alertas(m["inicio"] - 60, m["fin"])
    return {"marcas": m, "rutas_antes": antes, "rutas_durante": durante, "rutas_despues": despues,
            "alertmanager_durante_falla": am, "alertas": alertas}


# --------------------------------------------------------------------------
# Informe
# --------------------------------------------------------------------------
def _ms(v):
    return "-" if v is None else f"{v * 1000:.1f} ms"


def _pct(v):
    return "-" if v is None else f"{v * 100:.1f} %"


def _num(v, dec=1):
    return "-" if v is None else f"{v:.{dec}f}"


def _rel(t, base):
    return "no observado" if t is None else f"{t - base:+.0f} s"


def informe(etiqueta: str, meta: dict, A: dict, B: dict | None, capturas: list[str]) -> str:
    mk = A["marcas"]
    pf, cl, lt = A["prometheus_por_fase"], A["cliente"], A["linea_de_tiempo"]
    g = meta["git"]

    def pv(fase, serie, campo="promedio"):
        d = pf[fase].get(serie)
        return None if d is None else d[campo]

    l = [f"# Prueba de falla controlada {etiqueta}", "",
         "Generado por `monitoreo/scripts/ejecutar_prueba_controlada.py`. Todos los valores salen de "
         "Prometheus (paso de 15 s) o del registro del cliente de carga; nada es estimado.", "",
         f"- Commit: `{g.get('commit_corto')}` · Inicio: {iso(mk['inicio'])} · Fin A: {iso(mk['fin'])}",
         f"- Carga: {meta['usuarios']} usuarios virtuales en lazo cerrado, pausa 0,1-0,3 s, mezcla de "
         f"las 6 bases (ver `generar_carga.py`). Cache de comentarios: {meta['cache_verificada']}. "
         f"Corte rapido de la API (CORTOCIRCUITO_S): {meta.get('cortocircuito_s')}.",
         f"- Fases de {meta['fase_s']} s: normal → `docker stop fixture2030-redis` → `docker start fixture2030-redis`.",
         "- Volumenes: ninguno se borro (RNF11). Escrituras solo en partidos de laboratorio "
         f"`H13-{etiqueta}-P1/P2`.", "",
         "## A. Caida de Redis bajo carga", "",
         "### Lo que vio Prometheus (promedio de cada fase, sin su primer minuto)", "",
         "| Indicador | Normal | Falla (Redis detenido) | Recuperacion |",
         "| :-- | --: | --: | --: |",
         f"| Requests/s de la API | {_num(pv('normal','rps_api'))} | {_num(pv('falla','rps_api'))} | {_num(pv('recuperacion','rps_api'))} |",
         f"| Latencia p50 de la API | {_ms(pv('normal','p50_api_s'))} | {_ms(pv('falla','p50_api_s'))} | {_ms(pv('recuperacion','p50_api_s'))} |",
         f"| Latencia p95 de la API | {_ms(pv('normal','p95_api_s'))} | {_ms(pv('falla','p95_api_s'))} | {_ms(pv('recuperacion','p95_api_s'))} |",
         f"| Latencia p99 de la API | {_ms(pv('normal','p99_api_s'))} | {_ms(pv('falla','p99_api_s'))} | {_ms(pv('recuperacion','p99_api_s'))} |",
         f"| p95 de GET comentarios | {_ms(pv('normal','p95_comentarios_s'))} | {_ms(pv('falla','p95_comentarios_s'))} | {_ms(pv('recuperacion','p95_comentarios_s'))} |",
         f"| p95 de llamadas a Redis | {_ms(pv('normal','p95_dep_redis_s'))} | {_ms(pv('falla','p95_dep_redis_s'))} | {_ms(pv('recuperacion','p95_dep_redis_s'))} |",
         f"| p95 de llamadas a Cassandra | {_ms(pv('normal','p95_dep_cassandra_s'))} | {_ms(pv('falla','p95_dep_cassandra_s'))} | {_ms(pv('recuperacion','p95_dep_cassandra_s'))} |",
         f"| Lecturas que llegan a Cassandra (/s) | {_num(pv('normal','lecturas_cassandra_por_s'))} | {_num(pv('falla','lecturas_cassandra_por_s'))} | {_num(pv('recuperacion','lecturas_cassandra_por_s'))} |",
         f"| Aciertos de cache | {_pct(pv('normal','aciertos_cache'))} | {_pct(pv('falla','aciertos_cache'))} | {_pct(pv('recuperacion','aciertos_cache'))} |",
         f"| Tasa de errores 5xx | {_pct(pv('normal','tasa_5xx'))} | {_pct(pv('falla','tasa_5xx'))} | {_pct(pv('recuperacion','tasa_5xx'))} |",
         f"| Llamadas a Redis evitadas por el corte rapido (/s) | {_num(pv('normal','rechazos_corte_redis_por_s'))} | {_num(pv('falla','rechazos_corte_redis_por_s'))} | {_num(pv('recuperacion','rechazos_corte_redis_por_s'))} |",
         f"| redis_up (exporter, promedio) | {_num(pv('normal','redis_up_exporter'), 2)} | {_num(pv('falla','redis_up_exporter'), 2)} | {_num(pv('recuperacion','redis_up_exporter'), 2)} |",
         "", "### Lo que vio el cliente de carga", "",
         "| Fase | Requests | Requests/s | p50 | p95 | p99 | 5xx | Errores de conexion | Cache HIT/MISS |",
         "| :-- | --: | --: | --: | --: | --: | --: | --: | :-- |"]
    for f in (*FASES, "total"):
        c = cl[f]
        lc = c["latencia_cliente_ms"]
        cache = c["cache_lecturas_comentarios"]
        l.append(f"| {f} | {c['requests']} | {c['requests_por_segundo']} | {lc['p50']} ms | {lc['p95']} ms | "
                 f"{lc['p99']} ms | {c['errores_5xx']} | {c['errores_conexion_cliente']} | "
                 f"{cache.get('HIT', 0)}/{cache.get('MISS', 0)} |")
    l += ["", "### Linea de tiempo de deteccion y recuperacion", "",
          f"Referencias: falla = `docker stop` a los +{mk['falla'] - mk['inicio']:.0f} s; "
          f"recuperacion = `docker start` a los +{mk['recuperacion'] - mk['inicio']:.0f} s. "
          "Resolucion de 15 s (intervalo de scrape y de evaluacion).", "",
          "| Evento | Respecto de la falla | Respecto del docker start |", "| :-- | --: | --: |"]
    nombres = {"redis_up_exporter_en_0": "redis_up = 0 (exporter)",
               "redis_disponible_api_en_0": "La API ve Redis no disponible",
               "aciertos_cache_bajo_0_8": "Aciertos de cache < 80%",
               "redis_up_exporter_en_1": "redis_up = 1 de nuevo",
               "redis_disponible_api_en_1": "La API ve Redis disponible de nuevo",
               "aciertos_cache_vuelve_0_8": "Aciertos de cache >= 80% de nuevo"}
    for k, t in lt.items():
        nombre = nombres.get(k, k.replace("alerta_", "Alerta ").replace("_firing", " pasa a firing").replace("_", " "))
        l.append(f"| {nombre} | {_rel(t, mk['falla'])} | {_rel(t, mk['recuperacion']) if t and t >= mk['recuperacion'] else '-'} |")
    l += ["", "### Alertas durante el experimento A", "",
          "Tiempos relativos al `docker stop` de Redis. \"Ya activa\" = la alerta estaba disparada antes de "
          "empezar la carga (no la causo la prueba).", "",
          "| Alerta | Estado | Componente | Origen | Severidad | Desde | Hasta |",
          "| :-- | :-- | :-- | :-- | :-- | --: | --: |"]
    ini_rango = A["rango"][0]
    for al in A["alertas"]:
        desde = "ya activa" if al["desde"] <= ini_rango + PASO_S else _rel(al["desde"], mk["falla"])
        l.append(f"| {al['alerta']} | {al['estado']} | {al['componente']} | {al.get('origen', '')} | "
                 f"{al['severidad']} | {desde} | {_rel(al['hasta'], mk['falla'])} |")
    if not A["alertas"]:
        l.append("| (ninguna alerta paso a pending o firing) | | | | | |")
    if B:
        m = B["marcas"]
        l += ["", "## B. Caida de Cassandra sin carga", "",
              f"- `docker stop fixture2030-cassandra` a las {iso(m['inicio'])} (tardo {m['detenido'] - m['inicio']:.0f} s).",
              f"- La API ve Cassandra no disponible: {_rel(m['api_ve_caida'], m['detenido'])}.",
              f"- Alerta `BaseNoDisponible{{fuente=\"cassandra\"}}` en firing: {_rel(m['alerta_firing'], m['detenido'])} "
              "(for: 1m + intervalo de chequeo de 15 s + evaluacion de 15 s).",
              f"- `docker start` a las {iso(m['inicio_recuperacion'])}; la API la ve disponible "
              f"{_rel(m['api_ve_disponible'], m['inicio_recuperacion'])} y comentarios vuelve a 200 "
              f"{_rel(m['comentarios_200'], m['inicio_recuperacion'])}.", "",
              "| Fuente | Ruta | Antes | Con Cassandra caida | Despues |", "| :-- | :-- | :-- | :-- | :-- |"]
        for x, y, z in zip(B["rutas_antes"], B["rutas_durante"], B["rutas_despues"]):
            def f(r):
                return f"{r['http']}{(' ' + r['codigo_error']) if r['codigo_error'] else ''}"
            l.append(f"| {x['fuente']} | `{x['ruta']}` | {f(x)} | {f(y)} | {f(z)} |")
        l += ["", "Alertas del experimento B (tiempos relativos al `docker stop` de Cassandra; "
              "\"ya activa\" = disparada antes de empezar B):", ""]
        for al in B["alertas"]:
            desde = ("ya activa" if al["desde"] <= m["inicio"] - 60 + PASO_S
                     else _rel(al["desde"], m["detenido"]))
            l.append(f"- {al['alerta']} ({al['componente']}, {al.get('origen', '')}, {al['severidad']}) "
                     f"{al['estado']} desde {desde} hasta {_rel(al['hasta'], m['detenido'])}")
    l += ["", "## Archivos de esta corrida", "",
          "- `series_prometheus.csv`, `serie_cliente_5s.csv`, `alertas.json`, `metadata.json`",
          "- `requests_cliente.csv.gz` (una fila por request)",
          "- `alertmanager_durante_falla_*.json`" + (", `experimento_b_cassandra.json`" if B else ""), ""]
    if capturas:
        l += ["Capturas del tablero (rango exacto de la prueba):", ""]
        l += [f"- `../../dashboards/{c}`" for c in capturas]
    l += ["", "## Limites de esta medicion", "",
          "- Una sola maquina (Docker Desktop): bases, API, monitoreo y generador de carga comparten CPU.",
          "- Resolucion de 15 s: los tiempos de deteccion tienen un error de hasta un intervalo.",
          "- Los percentiles de Prometheus salen de buckets de histograma (aproximados); los del cliente son exactos.",
          ""]
    return "\n".join(l)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--usuarios", type=int, default=20)
    ap.add_argument("--fase", type=int, default=150, help="duracion de cada fase en segundos (min 90)")
    ap.add_argument("--etiqueta", default=None)
    ap.add_argument("--sin-cassandra", action="store_true", help="no ejecutar el experimento B")
    ap.add_argument("--sin-capturas", action="store_true")
    a = ap.parse_args(argv)
    if not os.environ.get("H13_PERMITIR_FASE_CORTA"):
        a.fase = max(a.fase, 90)   # con menos, el primer minuto de rate() tapa la fase entera
    etiqueta = a.etiqueta or etiqueta_nueva()
    dir_salida = DIR_EVIDENCIA / "prueba_de_falla" / etiqueta
    dir_salida.mkdir(parents=True, exist_ok=True)

    paso("Comprobando requisitos")
    problemas = []
    if http("GET", f"{PROMETHEUS}/-/ready", timeout=5)[0] != 200:
        problemas.append("Prometheus no responde en :9090 (scripts/iniciar_monitoreo).")
    if http("GET", f"{API}/openapi.json", timeout=5)[0] != 200:
        problemas.append("La API no responde en 127.0.0.1:8000.")
    elif prom_valor('max(up{job="api-fixture"})') != 1:
        problemas.append("Prometheus no logra leer /metrics de la API (target api-fixture DOWN).")
    for base in ("redis", "cassandra"):
        if contenedor_corriendo(CONTENEDORES[base]) is not True:
            problemas.append(f"El contenedor {CONTENEDORES[base]} no esta corriendo.")
    if problemas:
        for p in problemas:
            aviso(p)
        return 2
    cache = verificar_cache(etiqueta)
    cache_ok = cache == ["MISS", "HIT"]
    info(f"Cache de comentarios: {cache} ({'encendida' if cache_ok else 'NO verificada'})")
    if not cache_ok:
        aviso("La API no parece tener la cache encendida (CACHE_COMENTARIOS_TTL_S > 0). La prueba sigue, "
              "pero el efecto de la caida de Redis sobre la cache no se va a ver.")

    meta = {"etiqueta": etiqueta, "git": info_git(), "usuarios": a.usuarios, "fase_s": a.fase,
            "cache_verificada": "encendida (MISS y luego HIT)" if cache_ok else f"no verificada {cache}",
            # CORTOCIRCUITO_S con el que se levanto la API (lo informa ejecutar_todo_h13).
            "cortocircuito_s": os.environ.get("H13_CORTOCIRCUITO_S", "no informado"),
            "prometheus_scrape_s": 15, "inicio_utc": iso(time.time())}
    A = experimento_a(a, etiqueta, dir_salida, meta)
    mk = A["marcas"]
    meta.update({"marcas_utc": {k: iso(v) for k, v in mk.items()},
                 "partidos_de_laboratorio": partidos_de_laboratorio(etiqueta),
                 "ventanas_escritas": A["ventanas_escritas"]})
    escribir_json(dir_salida / "alertmanager_durante_falla_a.json", A["alertmanager_durante_falla"])

    B = None
    if not a.sin_cassandra:
        try:
            B = experimento_b(etiqueta)
            escribir_json(dir_salida / "experimento_b_cassandra.json",
                          {k: v for k, v in B.items() if k != "alertmanager_durante_falla"} |
                          {"marcas_utc": {k: (iso(v) if v else None) for k, v in B["marcas"].items()}})
            escribir_json(dir_salida / "alertmanager_durante_falla_b.json", B["alertmanager_durante_falla"])
        except Exception as e:  # el experimento A ya quedo medido: no perderlo
            aviso(f"El experimento B no se completo: {type(e).__name__}: {e}")
            if contenedor_corriendo(CONTENEDORES["cassandra"]) is False:
                docker("start", CONTENEDORES["cassandra"], timeout=180)

    escribir_json(dir_salida / "alertas.json", {"experimento_a": A["alertas"], "experimento_b": B["alertas"] if B else []})
    capturas = []
    if not a.sin_capturas:
        paso("Guardando capturas del tablero con el rango exacto de la prueba")
        import datetime as dt
        d = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc)
        capturas += capturar_dashboard.capturar(d(mk["inicio"] - 60), d(mk["fin"] + 45), f"prueba_{etiqueta}_A_redis")
        if B:
            capturas += capturar_dashboard.capturar(d(B["marcas"]["inicio"] - 90), d(B["marcas"]["fin"]),
                                                    f"prueba_{etiqueta}_B_cassandra")
    meta["fin_utc"] = iso(time.time())
    meta["capturas"] = capturas
    meta["resumen_a"] = {"cliente": A["cliente"], "prometheus_por_fase": A["prometheus_por_fase"],
                         "linea_de_tiempo_utc": {k: (iso(v) if v else None) for k, v in A["linea_de_tiempo"].items()}}
    escribir_json(dir_salida / "metadata.json", meta)
    escribir_texto(dir_salida / "resumen.md", informe(etiqueta, meta, A, B, capturas))
    paso(f"Listo. Informe: monitoreo/evidencia/prueba_de_falla/{etiqueta}/resumen.md")
    return 0


# --------------------------------------------------------------------------
# Operacion normal (sin fallas): las 6 bases bajo carga, para comparar bases
# --------------------------------------------------------------------------
def medir_operacion_normal(usuarios: int, duracion: int, etiqueta: str, capturas: bool = True) -> str:
    """Carga mixta sin fallas y comparacion entre las 6 bases (RF7, RF11).

    Evidencia: evidencia/operacion_normal/<etiqueta>/ (resumen.md, metadata.json,
    series_prometheus.csv, requests_cliente.csv.gz) y capturas operacion_<etiqueta>_*.png.
    """
    import datetime as dt
    dir_salida = DIR_EVIDENCIA / "operacion_normal" / etiqueta
    dir_salida.mkdir(parents=True, exist_ok=True)
    paso(f"Operacion normal: {usuarios} usuarios durante {duracion} s sobre las 6 bases")
    gen = GeneradorCarga(API, usuarios, etiqueta)
    inicio = time.time()
    gen.iniciar()
    anotar(f"H13 {etiqueta}: carga en operacion normal", ["hito13", "carga"], inicio)
    time.sleep(duracion)
    gen.detener()
    fin = gen.fin
    time.sleep(30)
    dur = int(fin - inicio)
    por_base = {}
    for clave, expr in {
        "p50_s": f"histogram_quantile(0.50, sum by (le, fuente) (increase(fixture_dependencia_duration_seconds_bucket[{dur}s])))",
        "p95_s": f"histogram_quantile(0.95, sum by (le, fuente) (increase(fixture_dependencia_duration_seconds_bucket[{dur}s])))",
        "ops_por_s": f"sum by (fuente) (increase(fixture_dependencia_duration_seconds_count{{resultado=\"ok\"}}[{dur}s])) / {dur}",
        "fallas_por_s": f"sum by (fuente) (increase(fixture_dependencia_duration_seconds_count{{resultado!=\"ok\"}}[{dur}s])) / {dur}",
    }.items():
        for r in prom_consulta(expr, fin):
            f = r["metric"].get("fuente", "?")
            try:
                v = float(r["value"][1])
            except ValueError:
                continue
            por_base.setdefault(f, {})[clave] = None if v != v else v
    total = {}
    for clave, expr in {
        "rps": f"sum(increase(fixture_api_requests_total[{dur}s])) / {dur}",
        "p50_s": f"histogram_quantile(0.50, sum by (le) (increase(fixture_api_request_duration_seconds_bucket[{dur}s])))",
        "p95_s": f"histogram_quantile(0.95, sum by (le) (increase(fixture_api_request_duration_seconds_bucket[{dur}s])))",
        "p99_s": f"histogram_quantile(0.99, sum by (le) (increase(fixture_api_request_duration_seconds_bucket[{dur}s])))",
        "tasa_5xx": f"(sum(increase(fixture_api_requests_total{{estado=~\"5..\"}}[{dur}s])) or vector(0)) / sum(increase(fixture_api_requests_total[{dur}s]))",
        "aciertos_cache": f"sum(increase(fixture_cache_comentarios_total{{estado=\"HIT\"}}[{dur}s])) / sum(increase(fixture_cache_comentarios_total{{estado=~\"HIT|MISS\"}}[{dur}s]))",
        "bases_disponibles": "sum(fixture_dependencia_disponible)",
        "targets_up": "sum(up)", "targets_total": "count(up)",
        "sondas_ok": "sum(probe_success)", "sondas_total": "count(probe_success)",
    }.items():
        total[clave] = prom_valor(expr, fin)
    cliente = resumir(gen.registros, inicio, fin)
    gen.guardar_csv(dir_salida / "requests_cliente.csv.gz")
    tiempos, datos = series_en_rango(inicio - 60, fin + 30)
    with open(dir_salida / "series_prometheus.csv", "w", encoding="utf-8", newline="") as fcsv:
        w = csv.writer(fcsv)
        w.writerow(["tiempo_utc", "segundos_desde_inicio", *SERIES.keys()])
        for t in tiempos:
            w.writerow([iso(t), round(t - inicio),
                        *[("" if datos[n].get(t) is None else round(datos[n][t], 6)) for n in SERIES]])
    hechas = []
    if capturas:
        d = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc)
        hechas = capturar_dashboard.capturar(d(inicio - 60), d(fin + 30), f"operacion_{etiqueta}")
    meta = {"etiqueta": etiqueta, "git": info_git(), "usuarios": usuarios, "duracion_s": dur,
            "inicio_utc": iso(inicio), "fin_utc": iso(fin),
            "cortocircuito_s": os.environ.get("H13_CORTOCIRCUITO_S", "no informado"),
            "api": total, "por_base": por_base, "cliente": cliente, "capturas": hechas,
            "partidos_de_laboratorio": partidos_de_laboratorio(etiqueta),
            "ventanas_escritas": sorted(gen.ventanas_escritas)}
    escribir_json(dir_salida / "metadata.json", meta)

    def ms(v):
        return "-" if v is None else f"{v * 1000:.1f} ms"

    def _n(v):
        return "-" if v is None else str(int(v))
    g = meta["git"]
    l = [f"# Operacion normal bajo carga {etiqueta}", "",
         "Generado por `monitoreo/scripts/ejecutar_prueba_controlada.py` (medir_operacion_normal). "
         "Valores de Prometheus sobre toda la ventana de carga y del registro del cliente.", "",
         f"- Commit: `{g.get('commit_corto')}` · {iso(inicio)} a {iso(fin)} ({dur} s)",
         f"- Carga: {usuarios} usuarios virtuales, mezcla de las 6 bases (`generar_carga.py`). "
         f"Corte rapido: CORTOCIRCUITO_S={meta['cortocircuito_s']}.",
         f"- Bases disponibles para la API al terminar: {_n(total.get('bases_disponibles'))}/6 · "
         f"targets UP: {_n(total.get('targets_up'))}/{_n(total.get('targets_total'))} · "
         f"sondas OK: {_n(total.get('sondas_ok'))}/{_n(total.get('sondas_total'))}", "",
         "## API (lo que ve Prometheus)", "",
         "| Requests/s | p50 | p95 | p99 | Errores 5xx | Aciertos de cache |", "| --: | --: | --: | --: | --: | --: |",
         f"| {total['rps'] or 0:.1f} | {ms(total['p50_s'])} | {ms(total['p95_s'])} | {ms(total['p99_s'])} | "
         f"{(total['tasa_5xx'] or 0) * 100:.2f} % | {(total['aciertos_cache'] or 0) * 100:.1f} % |", "",
         "## Comparacion entre bases (llamadas de la API a cada fuente, RF7)", "",
         "| Base | Operaciones/s | p50 | p95 | Fallas/s |", "| :-- | --: | --: | --: | --: |"]
    for f in sorted(por_base):
        b = por_base[f]
        l.append(f"| {f} | {b.get('ops_por_s') or 0:.1f} | {ms(b.get('p50_s'))} | {ms(b.get('p95_s'))} | "
                 f"{b.get('fallas_por_s') or 0:.2f} |")
    lc = cliente["latencia_cliente_ms"]
    l += ["", "## Cliente de carga", "",
          f"- {cliente['requests']} requests ({cliente['requests_por_segundo']}/s); p50 {lc['p50']} ms, "
          f"p95 {lc['p95']} ms, p99 {lc['p99']} ms; 5xx: {cliente['errores_5xx']}; errores de conexion: "
          f"{cliente['errores_conexion_cliente']}; 4xx: {cliente['respuestas_4xx']}.", "",
          "| Operacion | Requests | p95 cliente | Codigos HTTP |", "| :-- | --: | --: | :-- |"]
    for op, d_ in cliente["por_operacion"].items():
        l.append(f"| {op} | {d_['requests']} | {d_['p95_ms']} ms | {d_['codigos']} |")
    if hechas:
        l += ["", "Capturas:", ""] + [f"- `../../dashboards/{c}`" for c in hechas]
    escribir_texto(dir_salida / "resumen.md", "\n".join(l) + "\n")
    paso(f"Informe: monitoreo/evidencia/operacion_normal/{etiqueta}/resumen.md")
    return etiqueta


def main_seguro(argv=None) -> int:
    """main() con red de seguridad: pase lo que pase (error, Ctrl+C), las bases
    que la prueba detuvo se vuelven a iniciar. Nunca se borra nada."""
    try:
        return main(argv)
    finally:
        for base in ("redis", "cassandra"):
            if contenedor_corriendo(CONTENEDORES[base]) is False:
                aviso(f"Reiniciando {CONTENEDORES[base]}, que quedo detenido.")
                docker("start", CONTENEDORES[base], timeout=180)


if __name__ == "__main__":
    sys.exit(main_seguro())
