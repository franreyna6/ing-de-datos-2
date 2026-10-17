#!/usr/bin/env python3
"""Validacion del Hito 8: verifica que lo CARGADO coincide con lo GENERADO.

Etapa de validacion, separada de la generacion y de la carga (RF7, RF14).
Compara InfluxDB contra data/generado/<perfil>/manifest.json (que escribe
generacion_puntos.py) y contra los goles del Hito 5 (data/origen).

Verificaciones (cada una imprime PASS / FAIL / INFO con el dato observado):
  V1  el servidor responde (GET /health)
  V2  cantidad de puntos por tabla == manifest
  V3  distribucion de puntos por partido == manifest
  V4  cantidad de series por tabla == estimacion de cardinalidad del manifest
  V5  rango temporal (minimo y maximo) == manifest
  V6  valores finales de contadores == manifest y tiros >= goles (Hito 5)
  V7  posesion local + visitante = 100 en cada segundo (partido de referencia)
  V8  idempotencia: reenviar puntos ya cargados no cambia la cantidad
  V9  dato tardio: puntos que llegan fuera de orden se devuelven ordenados
  V10 conflicto de tipos: un field con otro tipo es rechazado (INFO)
  V11 los minutos de mayor interaccion coinciden con minutos de gol (Hito 5)

Uso: python scripts/validacion.py [--perfil local]
Codigo de salida: 0 si no hay FAIL.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_influx import (RAIZ, DB_VIVO, DB_LAB, Sesion, epoch_desde_iso)  # noqa: E402

TAGS = {  # tags que forman la serie de cada tabla
    "estadisticas_equipo": ["partido_id", "equipo_id"],
    "actividad_usuarios": ["partido_id", "region"],
    "metricas_plataforma": ["partido_id", "servicio"],
    "estadisticas_jugador": ["partido_id", "equipo_id", "jugador_id"],
}
REFERENCIA = "F2030-018"
resultados = []


def registrar(estado, nombre, detalle):
    resultados.append(estado)
    print("[%s] %s -- %s" % (estado, nombre, detalle))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--perfil", default="local")
    a = ap.parse_args()
    base = RAIZ / "data" / "generado" / a.perfil
    ruta_manifest = base / "manifest.json"
    if not ruta_manifest.exists():
        sys.exit("Falta %s. Ejecutar generacion_puntos.py --perfil %s"
                 % (ruta_manifest, a.perfil))
    mf = json.loads(ruta_manifest.read_text(encoding="utf-8"))
    ids = [p["codigo"] for p in mf["partidos_detalle"]]
    lista = ",".join("'%s'" % i for i in ids)
    s = Sesion()
    print("Validacion del perfil '%s': %d partidos, captura %d s, semilla %d"
          % (mf["perfil"], mf["partidos"], mf["duracion_captura_s"], mf["semilla"]))
    print("Rango temporal declarado: %s a +%d s"
          % (mf["partidos_detalle"][0]["inicio_utc"], mf["duracion_captura_s"]))
    print("-" * 78)

    # V1 ----------------------------------------------------------------
    try:
        estado = s.estado_servidor()
        registrar("PASS" if estado == 200 else "FAIL", "V1 servidor",
                  "GET /health -> HTTP %d" % estado)
    except Exception as exc:
        registrar("FAIL", "V1 servidor", str(exc))
        sys.exit(1)

    # V2, V3, V4, V5 ----------------------------------------------------
    for tabla, tags in TAGS.items():
        esperado = mf["tablas"][tabla]
        filtro = "partido_id IN (%s)" % lista
        n = int(s.consultar(DB_VIVO, "SELECT COUNT(*) AS n FROM %s WHERE %s"
                            % (tabla, filtro))[0]["n"])
        registrar("PASS" if n == esperado["puntos"] else "FAIL",
                  "V2 puntos en %s" % tabla,
                  "observado=%d esperado=%d" % (n, esperado["puntos"]))

        filas = s.consultar(DB_VIVO, "SELECT partido_id, COUNT(*) AS n FROM %s "
                                     "WHERE %s GROUP BY partido_id" % (tabla, filtro))
        obs = {f["partido_id"]: int(f["n"]) for f in filas}
        difs = [k for k in esperado["por_partido"]
                if obs.get(k) != esperado["por_partido"][k]]
        registrar("PASS" if not difs and len(obs) == len(ids) else "FAIL",
                  "V3 distribucion por partido en %s" % tabla,
                  "%d partidos, %s" % (len(obs), "todos coinciden"
                                       if not difs else "difieren: %s" % difs[:5]))

        cols = ", ".join(tags)
        ns = int(s.consultar(
            DB_VIVO, "SELECT COUNT(*) AS n FROM (SELECT %s FROM %s WHERE %s "
                     "GROUP BY %s) AS series" % (cols, tabla, filtro, cols))[0]["n"])
        registrar("PASS" if ns == esperado["series"] else "FAIL",
                  "V4 series en %s" % tabla,
                  "observado=%d esperado=%d (tags: %s)"
                  % (ns, esperado["series"], cols))

        r = s.consultar(DB_VIVO, "SELECT MIN(time) AS t0, MAX(time) AS t1 FROM %s "
                                 "WHERE %s" % (tabla, filtro))[0]
        t0, t1 = epoch_desde_iso(r["t0"]), epoch_desde_iso(r["t1"])
        registrar("PASS" if (t0, t1) == (esperado["ts_min"], esperado["ts_max"])
                  else "FAIL", "V5 rango temporal de %s" % tabla,
                  "observado=%d..%d esperado=%d..%d"
                  % (t0, t1, esperado["ts_min"], esperado["ts_max"]))

    # V6 ----------------------------------------------------------------
    filas = s.consultar(
        DB_VIVO, "SELECT partido_id, equipo_id, MAX(tiros_acum) AS tiros, "
                 "MAX(pases_acum) AS pases, MAX(recuperaciones_acum) AS rec "
                 "FROM estadisticas_equipo WHERE partido_id IN (%s) "
                 "GROUP BY partido_id, equipo_id" % lista)
    obs = {(f["partido_id"], f["equipo_id"]): (int(f["tiros"]), int(f["pases"]),
                                              int(f["rec"])) for f in filas}
    malos, bajo_goles = [], []
    for p in mf["partidos_detalle"]:
        for eq, e in p["equipos"].items():
            esp = (e["tiros_final"], e["pases_final"], e["recuperaciones_final"])
            if obs.get((p["codigo"], eq)) != esp:
                malos.append((p["codigo"], eq))
            if obs.get((p["codigo"], eq), (0,))[0] < e["goles"]:
                bajo_goles.append((p["codigo"], eq))
    registrar("PASS" if not malos else "FAIL", "V6a contadores finales",
              "%d equipos-partido comparados con el manifest, %d difieren"
              % (len(obs), len(malos)))
    registrar("PASS" if not bajo_goles else "FAIL",
              "V6b coherencia con el Hito 5",
              "tiros finales >= goles de partidos.csv en %d de %d equipos-partido"
              % (len(obs) - len(bajo_goles), len(obs)))

    # V7 ----------------------------------------------------------------
    r = s.consultar(
        DB_VIVO, "SELECT COUNT(*) AS n FROM (SELECT time FROM estadisticas_equipo "
                 "WHERE partido_id = '%s' GROUP BY time "
                 "HAVING ABS(SUM(posesion_pct) - 100.0) > 0.05) AS malos" % REFERENCIA)
    registrar("PASS" if int(r[0]["n"]) == 0 else "FAIL",
              "V7 posesion local+visitante = 100",
              "segundos que no suman 100 en %s: %s" % (REFERENCIA, r[0]["n"]))

    # V8 ----------------------------------------------------------------
    with open(base / "estadisticas_equipo.lp", encoding="utf-8") as f:
        lote = [next(f).rstrip("\n") for _ in range(2000)]
    antes = int(s.consultar(DB_VIVO, "SELECT COUNT(*) AS n FROM estadisticas_equipo "
                                     "WHERE partido_id IN (%s)" % lista)[0]["n"])
    est, txt = s.escribir(DB_VIVO, "\n".join(lote) + "\n")
    despues = int(s.consultar(DB_VIVO, "SELECT COUNT(*) AS n FROM estadisticas_equipo "
                                       "WHERE partido_id IN (%s)" % lista)[0]["n"])
    registrar("PASS" if est in (200, 204) and antes == despues else "FAIL",
              "V8 idempotencia",
              "se reenviaron 2000 puntos ya cargados (HTTP %d): antes=%d despues=%d"
              % (est, antes, despues))

    # V9 ----------------------------------------------------------------
    t = mf["partidos_detalle"][0]["inicio_epoch_s"]
    etiqueta = "estadisticas_equipo,partido_id=LAB-TARDIO,equipo_id=LAB,sede=LAB,grupo=Z"
    for desp in (300, 100, 200):          # el punto de +100 llega TARDE
        est, _ = s.escribir(DB_LAB, "%s posesion_pct=50.0,pases_acum=%di,tiros_acum=0i,"
                                    "recuperaciones_acum=0i %d\n" % (etiqueta, desp, t + desp))
    filas = s.consultar(DB_LAB, "SELECT time, pases_acum FROM estadisticas_equipo "
                                "WHERE partido_id = 'LAB-TARDIO' ORDER BY time")
    orden = [int(f["pases_acum"]) for f in filas]
    registrar("PASS" if orden == [100, 200, 300] else "FAIL", "V9 dato tardio",
              "orden de llegada 300,100,200 -> consulta devuelve %s" % orden)

    # V10 ---------------------------------------------------------------
    est, txt = s.escribir(DB_LAB, "%s posesion_pct=58i,pases_acum=1i,tiros_acum=0i,"
                                  "recuperaciones_acum=0i %d\n" % (etiqueta, t + 400))
    registrar("INFO", "V10 conflicto de tipos",
              "posesion_pct float reescrito como entero -> HTTP %d (%s)"
              % (est, "rechazado" if est >= 400 else "aceptado")
              + ("; respuesta: " + txt[:120].replace("\n", " ") if est >= 400 else ""))

    # V11 ---------------------------------------------------------------
    if mf["duracion_captura_s"] >= 5400:
        goles = []
        with open(RAIZ / "data" / "origen" / "eventos.csv", encoding="utf-8") as f:
            for e in csv.DictReader(f):
                if e["partidoCodigo"] == REFERENCIA and e["tipo"] == "Gol":
                    goles.append(int(e["minuto"]))
        ini = mf["partidos_detalle"][0]["inicio_epoch_s"]
        filas = s.consultar(
            DB_VIVO, "SELECT date_trunc('minute', time) AS minuto, "
                     "SUM(interacciones) AS n FROM actividad_usuarios "
                     "WHERE partido_id = '%s' GROUP BY date_trunc('minute', time) "
                     "ORDER BY n DESC LIMIT 3" % REFERENCIA)
        minutos = [(epoch_desde_iso(f["minuto"]) - ini) // 60 for f in filas]
        ok = all(any(g <= m <= g + 4 for g in goles) for m in minutos[:1])
        registrar("PASS" if ok else "FAIL", "V11 interaccion vs goles (Hito 5)",
                  "minutos de gol=%s | 3 minutos de mayor interaccion=%s"
                  % (sorted(goles), minutos))
    else:
        registrar("INFO", "V11 interaccion vs goles",
                  "omitida: el perfil dura menos de 5400 s")

    print("-" * 78)
    print("Resumen: %d PASS, %d FAIL, %d INFO"
          % (resultados.count("PASS"), resultados.count("FAIL"),
             resultados.count("INFO")))
    sys.exit(1 if "FAIL" in resultados else 0)


if __name__ == "__main__":
    main()
