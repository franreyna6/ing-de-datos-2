#!/usr/bin/env python3
"""Generacion reproducible de puntos de estadisticas en vivo (Hito 8).

Esta etapa SOLO genera archivos de line protocol; no toca InfluxDB. La carga
(carga_lotes.py) y la validacion (validacion.py) son etapas separadas (RF7).

Los datos son SIMULADOS pero estan anclados a los CSV del Hito 5
(data/origen/): partidos, fechas, sedes, equipos, plantillas, goles y minutos
de gol. Con la misma semilla el resultado es identico byte a byte.

Tablas generadas (ver docs/modelo_multidimensional.md):
  estadisticas_equipo   1 punto/s por (partido, equipo)
  actividad_usuarios    1 punto/s por (partido, region)
  metricas_plataforma   1 punto/s por (partido, servicio)
  estadisticas_jugador  1 punto cada 5 s por (partido, jugador titular)

Precision de timestamps: segundos (se declara al escribir: precision=second).

Perfiles (partidos x duracion de captura):
  muestra   2 partidos  x   600 s  ->      22.080 puntos (prueba rapida)
  local    12 partidos  x  6000 s  ->   1.324.800 puntos (laboratorio)
  completo 96 partidos  x  6000 s  ->  10.598.400 puntos (objetivo 10M+)

Uso:
  python scripts/generacion_puntos.py --perfil local
  python scripts/generacion_puntos.py --perfil completo --solo-contar
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import random
import time
import zlib
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / "data" / "origen"
SALIDA_BASE = RAIZ / "data" / "generado"

SEMILLA = 2030
PASO_JUGADOR_S = 5
# Horarios de inicio (UTC) por orden dentro del dia: hasta 6 partidos por dia
# en el calendario del Hito 5; 3 h de separacion para 100 min de captura.
HORAS_INICIO = [8, 11, 14, 17, 20, 23]
REGIONES = [("LATAM", 0.30), ("EUROPA", 0.28), ("NORTEAMERICA", 0.14),
            ("AFRICA", 0.12), ("ASIA", 0.12), ("OCEANIA", 0.04)]
# servicio: (latencia base ms, solicitudes por segundo base)
SERVICIOS = {"api_fixture": (45.0, 800), "streaming": (120.0, 300),
             "comentarios": (60.0, 500), "cache": (3.0, 2500),
             "estadisticas": (35.0, 700), "notificaciones": (80.0, 200)}
PERFILES = {"muestra": (2, 600), "local": (12, 6000), "completo": (96, 6000)}
TABLAS = ["estadisticas_equipo", "actividad_usuarios",
          "metricas_plataforma", "estadisticas_jugador"]
# (media, desvio) de velocidad en km/h por posicion; promedios bajos porque
# incluyen caminata y pausas (~9-11 km por jugador en 100 min de captura).
PERFIL_POSICION = {"Arquero": (2.0, 1.5), "Defensor": (5.5, 2.8),
                   "Mediocampista": (6.8, 3.2), "Delantero": (6.2, 3.2)}
TITULARES = {"Arquero": 1, "Defensor": 4, "Mediocampista": 4, "Delantero": 2}


def leer(nombre):
    with open(ORIGEN / (nombre + ".csv"), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def semilla(*partes):
    return ":".join(str(x) for x in (SEMILLA,) + partes)


def cargar_contexto():
    partidos = leer("partidos")
    equipos = {e["codigo"]: e for e in leer("equipos")}
    sedes = {s["codigo"]: s for s in leer("sedes")}
    participaciones = defaultdict(dict)
    for r in leer("participaciones"):
        participaciones[r["partidoCodigo"]][r["condicion"]] = r["equipoCodigo"]
    plantillas = defaultdict(list)
    for j in leer("jugadores"):
        plantillas[j["equipoCodigo"]].append(j)
    goles_ev = defaultdict(list)          # (partido, equipo) -> [(codigo, minuto)]
    for e in leer("eventos"):
        if e["tipo"] == "Gol":
            equipo = e["jugadorCodigo"].split("-")[0]
            goles_ev[(e["partidoCodigo"], equipo)].append(
                (e["codigo"], int(e["minuto"])))
    # Orden cronologico y horario de inicio por orden dentro del dia.
    partidos.sort(key=lambda p: (p["fecha"], p["codigo"]))
    por_dia = defaultdict(int)
    for p in partidos:
        idx = por_dia[p["fecha"]]
        por_dia[p["fecha"]] += 1
        y, m, d = (int(x) for x in p["fecha"].split("-"))
        inicio = dt.datetime(y, m, d, HORAS_INICIO[idx], tzinfo=dt.timezone.utc)
        p["_inicio"] = int(inicio.timestamp())
        p["_inicio_iso"] = inicio.strftime("%Y-%m-%dT%H:%M:%SZ")
    return partidos, equipos, sedes, participaciones, plantillas, goles_ev


def titulares(plantilla):
    """11 titulares determinísticos: 1 arquero, 4 defensores, 4 medios y 2
    delanteros, por dorsal ascendente dentro de cada posicion."""
    elegidos = []
    for pos, n in TITULARES.items():
        grupo = sorted((j for j in plantilla if j["posicion"] == pos),
                       key=lambda j: int(j["dorsal"]))
        elegidos += grupo[:n]
    return elegidos


def fmt1(x):
    return "%.1f" % x


def generar_partido(p, ctx, dur, salida, cuenta_series):
    """Genera las lineas de un partido. Devuelve (dict tabla->lista de
    lineas, esperados por equipo)."""
    (_, equipos, _, participaciones, plantillas, goles_ev, rank_max) = ctx
    cod = p["codigo"]
    sede, grupo, t0 = p["sedeCodigo"], p["grupo"], p["_inicio"]
    loc = participaciones[cod]["local"]
    vis = participaciones[cod]["visitante"]
    rl, rv = int(equipos[loc]["rankingFIFA"]), int(equipos[vis]["rankingFIFA"])
    popularidad = 0.4 + 1.6 * (1 - (rl + rv) / (2.0 * rank_max))
    goles = {loc: int(p["golesLocal"]), vis: int(p["golesVisitante"])}

    # ---- goles (segundos de captura) y picos de interes ------------------
    rng = random.Random(semilla(cod, "eventos"))
    seg_gol = {loc: [], vis: []}
    for eq in (loc, vis):
        evs = goles_ev.get((cod, eq), [])
        for codigo_ev, minuto in evs:
            s = minuto * 60 + zlib.crc32(codigo_ev.encode()) % 60
            seg_gol[eq].append(s if s < dur else rng.randrange(dur))
        while len(seg_gol[eq]) < goles[eq]:       # por si faltara un evento
            seg_gol[eq].append(rng.randrange(dur))
    pico = [0.0] * dur
    for eq in (loc, vis):
        for g in seg_gol[eq]:
            for t in range(g, min(dur, g + 240)):
                pico[t] += math.exp(-(t - g) / 50.0)
    rampa = []
    for t in range(dur):
        r = min(1.0, 0.3 + 0.7 * t / 600.0)
        if t > dur - 300:
            r *= 1 - 0.2 * (t - (dur - 300)) / 300.0
        rampa.append(r)

    lineas = {}
    esperados = {}

    # ---- estadisticas_equipo ---------------------------------------------
    rng = random.Random(semilla(cod, "equipo"))
    base_loc = 50.0 + 10.0 * (rv - rl) / rank_max
    pos_loc = base_loc
    estado = {}
    for eq in (loc, vis):
        tiros = [0] * dur
        for s in seg_gol[eq]:
            tiros[s] += 1
        for _ in range(rng.randint(6, 14)):
            tiros[rng.randrange(dur)] += 1
        estado[eq] = {"p_pase": rng.uniform(0.07, 0.11),
                      "p_rec": rng.uniform(0.02, 0.04), "tiros": tiros,
                      "pases": 0, "rec": 0, "tcum": 0}
    pref = {eq: ("estadisticas_equipo,partido_id=%s,equipo_id=%s,sede=%s,"
                 "grupo=%s " % (cod, eq, sede, grupo)) for eq in (loc, vis)}
    out = []
    for t in range(dur):
        pos_loc += rng.gauss(0, 0.15) + 0.002 * (base_loc - pos_loc)
        pos_loc = min(70.0, max(30.0, pos_loc))
        l10 = int(round(pos_loc * 10))
        pos = {loc: l10, vis: 1000 - l10}
        ts = t0 + t
        for eq in (loc, vis):
            e = estado[eq]
            if rng.random() < e["p_pase"]:
                e["pases"] += 1
            if rng.random() < e["p_rec"]:
                e["rec"] += 1
            e["tcum"] += e["tiros"][t]
            out.append("%sposesion_pct=%d.%d,pases_acum=%di,tiros_acum=%di,"
                       "recuperaciones_acum=%di %d"
                       % (pref[eq], pos[eq] // 10, pos[eq] % 10, e["pases"],
                          e["tcum"], e["rec"], ts))
    lineas["estadisticas_equipo"] = out
    for eq in (loc, vis):
        e = estado[eq]
        esperados[eq] = {"goles": goles[eq], "tiros_final": e["tcum"],
                         "pases_final": e["pases"],
                         "recuperaciones_final": e["rec"]}

    # ---- actividad_usuarios ----------------------------------------------
    rng = random.Random(semilla(cod, "usuarios"))
    base = {r: 20000.0 * popularidad * w for r, w in REGIONES}
    prefr = {r: "actividad_usuarios,partido_id=%s,region=%s " % (cod, r)
             for r, _ in REGIONES}
    out = []
    for t in range(dur):
        ts = t0 + t
        k = rampa[t]
        s = pico[t]
        for r, _ in REGIONES:
            u = int(base[r] * k * (1 + 0.5 * s) * (1 + rng.gauss(0, 0.01)))
            inter = int(u * (0.004 + 0.02 * s) * (0.5 + rng.random()))
            out.append("%susuarios_conectados=%di,interacciones=%di %d"
                       % (prefr[r], u, inter, ts))
    lineas["actividad_usuarios"] = out

    # ---- metricas_plataforma ---------------------------------------------
    rng = random.Random(semilla(cod, "plataforma"))
    prefs = {s: "metricas_plataforma,partido_id=%s,servicio=%s " % (cod, s)
             for s in SERVICIOS}
    out = []
    for t in range(dur):
        ts = t0 + t
        carga = rampa[t] * popularidad * (1 + 0.6 * pico[t])
        pe = 0.002 + 0.01 * pico[t]
        for s, (lat_base, rps) in SERVICIOS.items():
            lat = lat_base * (1 + 0.5 * carga) + abs(rng.gauss(0, lat_base * 0.08))
            sol = int(rps * carga * (0.8 + 0.4 * rng.random()))
            err = 1 if rng.random() < pe else 0
            out.append("%slatencia_ms=%.2f,solicitudes=%di,errores=%di %d"
                       % (prefs[s], lat, sol, err, ts))
    lineas["metricas_plataforma"] = out

    # ---- estadisticas_jugador --------------------------------------------
    rng = random.Random(semilla(cod, "jugadores"))
    jug = []
    for eq in (loc, vis):
        for j in titulares(plantillas[eq]):
            mu, sd = PERFIL_POSICION[j["posicion"]]
            jug.append(["estadisticas_jugador,partido_id=%s,equipo_id=%s,"
                        "jugador_id=%s " % (cod, eq, j["codigo"]), mu, sd, 0.0])
    out = []
    for t in range(0, dur, PASO_JUGADOR_S):
        ts = t0 + t
        for j in jug:
            v = min(34.0, max(0.0, rng.gauss(j[1], j[2])))
            j[3] += v / 3.6 * PASO_JUGADOR_S
            out.append("%svelocidad_kmh=%.1f,distancia_acum_m=%.1f %d"
                       % (j[0], v, j[3], ts))
    lineas["estadisticas_jugador"] = out

    cuenta_series["estadisticas_equipo"] += 2
    cuenta_series["actividad_usuarios"] += len(REGIONES)
    cuenta_series["metricas_plataforma"] += len(SERVICIOS)
    cuenta_series["estadisticas_jugador"] += len(jug)
    return lineas, esperados


def elegir_partidos(partidos, n):
    total = len(partidos)
    n = min(n, total)
    return [partidos[int(i * total / n)] for i in range(n)]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--perfil", choices=sorted(PERFILES), default="local")
    ap.add_argument("--partidos", type=int, help="sobrescribe la cantidad")
    ap.add_argument("--duracion", type=int, help="segundos de captura/partido")
    ap.add_argument("--salida", help="directorio de salida")
    ap.add_argument("--solo-contar", action="store_true",
                    help="genera y cuenta sin escribir archivos")
    a = ap.parse_args()

    n_part, dur = PERFILES[a.perfil]
    n_part = a.partidos or n_part
    dur = a.duracion or dur
    partidos, equipos, sedes, partic, plant, goles_ev = cargar_contexto()
    rank_max = max(int(e["rankingFIFA"]) for e in equipos.values())
    ctx = (partidos, equipos, sedes, partic, plant, goles_ev, rank_max)
    elegidos = elegir_partidos(partidos, n_part)
    nombre_perfil = a.perfil if not (a.partidos or a.duracion) else "personalizado"
    destino = Path(a.salida) if a.salida else SALIDA_BASE / nombre_perfil

    manejadores, hashes = {}, {}
    if not a.solo_contar:
        destino.mkdir(parents=True, exist_ok=True)
        for tabla in TABLAS:
            manejadores[tabla] = open(destino / (tabla + ".lp"), "wb")
            hashes[tabla] = hashlib.sha256()

    puntos = defaultdict(int)
    por_partido = defaultdict(dict)
    series = defaultdict(int)
    manifest_partidos = []
    t_ini = time.time()
    for i, p in enumerate(elegidos, 1):
        lineas, esperados = generar_partido(p, ctx, dur, destino, series)
        for tabla in TABLAS:
            n = len(lineas[tabla])
            puntos[tabla] += n
            por_partido[tabla][p["codigo"]] = n
            if not a.solo_contar:
                datos = ("\n".join(lineas[tabla]) + "\n").encode("utf-8")
                manejadores[tabla].write(datos)
                hashes[tabla].update(datos)
        manifest_partidos.append({
            "codigo": p["codigo"], "fecha": p["fecha"], "grupo": p["grupo"],
            "sede": p["sedeCodigo"], "inicio_epoch_s": p["_inicio"],
            "inicio_utc": p["_inicio_iso"],
            "local": partic[p["codigo"]]["local"],
            "visitante": partic[p["codigo"]]["visitante"],
            "equipos": esperados})
        if i % 4 == 0 or i == len(elegidos):
            print("  generado %d/%d partidos (%.0f s)"
                  % (i, len(elegidos), time.time() - t_ini), flush=True)
    seg = time.time() - t_ini
    for fh in manejadores.values():
        fh.close()

    inicio_min = min(p["_inicio"] for p in elegidos)
    inicio_max = max(p["_inicio"] for p in elegidos)
    ultimo_jug = ((dur - 1) // PASO_JUGADOR_S) * PASO_JUGADOR_S
    manifest = {
        "perfil": nombre_perfil, "semilla": SEMILLA, "partidos": len(elegidos),
        "duracion_captura_s": dur, "paso_jugador_s": PASO_JUGADOR_S,
        "precision_timestamp": "segundos (precision=second)",
        "generado_utc": dt.datetime.now(dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "tablas": {t: {"puntos": puntos[t], "series": series[t],
                       "por_partido": por_partido[t],
                       "ts_min": inicio_min,
                       "ts_max": inicio_max + (ultimo_jug if t == "estadisticas_jugador"
                                               else dur - 1),
                       "sha256": hashes[t].hexdigest() if hashes else None}
                   for t in TABLAS},
        "partidos_detalle": manifest_partidos,
    }
    total = sum(puntos.values())
    if not a.solo_contar:
        with open(destino / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=1, ensure_ascii=False)

    print("Perfil: %s | partidos: %d | captura: %d s | semilla: %d"
          % (nombre_perfil, len(elegidos), dur, SEMILLA))
    print("%-22s %12s %8s" % ("tabla", "puntos", "series"))
    for t in TABLAS:
        print("%-22s %12d %8d" % (t, puntos[t], series[t]))
    print("%-22s %12d" % ("TOTAL", total))
    print("Generacion: %.1f s (%.0f puntos/s generados)%s"
          % (seg, total / seg if seg else 0,
             "" if not a.solo_contar else " [solo conteo, sin escribir]"))
    if not a.solo_contar:
        print("Salida: %s" % destino)


if __name__ == "__main__":
    main()
