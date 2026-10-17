#!/usr/bin/env python3
"""Carga por lotes de line protocol hacia InfluxDB 3 Core (Hito 8).

Etapa de CARGA, separada de la generacion y de la validacion (RF7).
Lee data/generado/<perfil>/*.lp y escribe con POST /api/v3/write_lp
declarando la precision (segundos).

Estrategia (ver docs/cardinalidad_y_escalabilidad.md, seccion "Carga"):
  - tamano de lote configurable (por defecto 5.000 lineas);
  - concurrencia configurable (por defecto 4 hilos, una conexion por hilo,
    con cola acotada para no acumular lotes en memoria);
  - reintentos con espera exponencial solo ante errores transitorios
    (conexion, HTTP 5xx, 429). Un 4xx (por ejemplo conflicto de tipos o
    line protocol invalido) NO se reintenta: el lote va a rechazados.lp;
  - escribir de nuevo el mismo punto (misma serie y timestamp) lo
    reemplaza, por lo que reintentar un lote es idempotente;
  - --desorden baraja las lineas dentro de cada lote para comprobar que el
    orden de llegada no altera el resultado;
  - --medir-lotes compara tamanos de lote y concurrencias sobre una muestra,
    en la base descartable fixture2030_lab, desplazando los timestamps para
    que cada corrida inserte puntos nuevos (comparacion justa).

Uso:
  python scripts/carga_lotes.py --perfil local
  python scripts/carga_lotes.py --perfil local --tamano-lote 10000 --concurrencia 8
  python scripts/carga_lotes.py --perfil local --medir-lotes
"""
import argparse
import itertools
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_influx import (RAIZ, DB_VIVO, DB_LAB, HOST, PRECISION, PUERTO,  # noqa: E402
                        Sesion, leer_token)

TABLAS = ["estadisticas_equipo", "actividad_usuarios",
          "metricas_plataforma", "estadisticas_jugador"]
ESTADOS_REINTENTABLES = {429, 500, 502, 503, 504}

_local = threading.local()


def _sesion(token):
    if not hasattr(_local, "s"):
        _local.s = Sesion(token=token)
    return _local.s


def enviar_lote(token, db, lineas, reintentos, desorden, abortar=None):
    """Envia un lote. Devuelve (n_lineas, ok, intentos, segundos, detalle)."""
    if abortar is not None and abortar.is_set():
        return len(lineas), False, 0, 0.0, "abortado"
    if desorden:
        random.shuffle(lineas)
    cuerpo = ("\n".join(lineas) + "\n").encode("utf-8")
    t0 = time.time()
    detalle = ""
    for intento in range(1, reintentos + 2):
        try:
            estado, texto = _sesion(token).escribir(db, cuerpo)
            if estado in (200, 204):
                return len(lineas), True, intento, time.time() - t0, ""
            detalle = "HTTP %d: %s" % (estado, texto[:300].replace("\n", " "))
            if estado not in ESTADOS_REINTENTABLES:
                break                       # error permanente: no reintentar
        except Exception as exc:           # conexion caida, timeout, etc.
            detalle = "%s: %s" % (type(exc).__name__, exc)
        if abortar is not None and abortar.is_set():
            break
        time.sleep(min(30, 0.5 * 2 ** (intento - 1)))
    return len(lineas), False, intento, time.time() - t0, detalle


def leer_lotes(ruta, tamano, max_lineas=None, desplazamiento_s=0):
    """Genera listas de lineas de `tamano`. Opcionalmente limita la cantidad
    y desplaza los timestamps (solo para --medir-lotes)."""
    leidas = 0
    with open(ruta, encoding="utf-8") as f:
        while True:
            lote = [l.rstrip("\n") for l in itertools.islice(f, tamano)]
            if not lote:
                return
            if max_lineas is not None and leidas + len(lote) > max_lineas:
                lote = lote[:max_lineas - leidas]
            if desplazamiento_s:
                nuevo = []
                for l in lote:
                    cabeza, ts = l.rsplit(" ", 1)
                    nuevo.append("%s %d" % (cabeza, int(ts) + desplazamiento_s))
                lote = nuevo
            leidas += len(lote)
            yield lote
            if max_lineas is not None and leidas >= max_lineas:
                return


def cargar_archivo(token, db, ruta, tamano, concurrencia, reintentos,
                   desorden, rechazados, max_lineas=None, desplazamiento_s=0,
                   silencioso=False, max_fallos_seguidos=5):
    """Carga un archivo con una cola acotada de lotes en vuelo.

    Si fallan `max_fallos_seguidos` lotes consecutivos (servidor caido o sin
    memoria) se aborta con un mensaje claro en lugar de seguir reintentando
    lote tras lote.
    """
    stats = {"lineas": 0, "ok": 0, "lotes": 0, "lotes_fallidos": 0,
             "reintentos": 0, "seg_lotes": 0.0}
    abortar = threading.Event()
    seguidos = [0]
    ultimo_error = [""]
    en_vuelo = set()
    t0 = time.time()
    ultimo_aviso = t0
    with ThreadPoolExecutor(max_workers=concurrencia) as pool:
        def recoger(terminados):
            for fut in terminados:
                n, ok, intentos, seg, detalle = fut.result()
                lote_lineas = fut.lineas
                if detalle == "abortado":
                    continue
                stats["lotes"] += 1
                stats["seg_lotes"] += seg
                stats["reintentos"] += intentos - 1
                if ok:
                    stats["ok"] += n
                    seguidos[0] = 0
                else:
                    stats["lotes_fallidos"] += 1
                    seguidos[0] += 1
                    ultimo_error[0] = detalle
                    if seguidos[0] >= max_fallos_seguidos:
                        abortar.set()
                    print("  ! lote rechazado (%d lineas, %d intentos): %s"
                          % (n, intentos, detalle), flush=True)
                    with open(rechazados, "a", encoding="utf-8") as rej:
                        rej.write("\n".join(lote_lineas) + "\n")

        for lote in leer_lotes(ruta, tamano, max_lineas, desplazamiento_s):
            stats["lineas"] += len(lote)
            fut = pool.submit(enviar_lote, token, db, lote, reintentos,
                              desorden, abortar)
            fut.lineas = lote
            en_vuelo.add(fut)
            if len(en_vuelo) >= concurrencia * 2:      # cola acotada
                hechos, en_vuelo = wait(en_vuelo, return_when=FIRST_COMPLETED)
                recoger(hechos)
            if abortar.is_set():
                break
            ahora = time.time()
            if not silencioso and ahora - ultimo_aviso >= 5:
                print("  ... %s: %d lineas enviadas (%.0f s)"
                      % (ruta.name, stats["lineas"], ahora - t0),
                      flush=True)
                ultimo_aviso = ahora
        hechos, _ = wait(en_vuelo)
        recoger(hechos)
    stats["segundos"] = time.time() - t0
    if abortar.is_set():
        sys.exit("\nCARGA ABORTADA: fallaron %d lotes seguidos (ultimo error: %s).\n"
                 "Causas probables: Docker Desktop cerrado, contenedor caido o sin "
                 "memoria. Revisar: docker compose ps  y  docker logs --tail 40 "
                 "fixture2030-influxdb. La carga es idempotente: al repetirla se "
                 "reemplazan los puntos ya escritos." % (max_fallos_seguidos,
                                                         ultimo_error[0][:160]))
    return stats


def verificar_servidor(token):
    """Comprueba que el servidor responde ANTES de generar trafico."""
    try:
        estado = Sesion(token=token, timeout=10).estado_servidor()
    except Exception as exc:
        sys.exit("El servidor no responde en %s:%d (%s).\nVerificar que Docker "
                 "Desktop este abierto y el contenedor activo: docker compose ps"
                 % (HOST, PUERTO, exc))
    if estado != 200:
        sys.exit("El servidor respondio HTTP %d en /health; se esperaba 200."
                 % estado)


def medir_lotes(token, ruta_base, max_lineas):
    """Compara tamanos de lote y concurrencia sobre una muestra (lab)."""
    ruta = ruta_base / "actividad_usuarios.lp"
    print("== Medicion de tamano de lote y concurrencia ==", flush=True)
    print("Archivo: %s | primeras %d lineas | base: %s (descartable)"
          % (ruta.name, max_lineas, DB_LAB), flush=True)
    print("%-12s %-12s %12s %10s %12s %10s"
          % ("tamano_lote", "concurrencia", "lineas_ok", "segundos",
             "puntos/s", "reintentos"), flush=True)
    resultados = []
    corrida = 0
    for tamano in (500, 5000, 20000):
        for conc in (1, 4):
            corrida += 1
            st = cargar_archivo(token, DB_LAB, ruta, tamano, conc, 3, False,
                                ruta_base / "rechazados_medicion.lp",
                                max_lineas=max_lineas,
                                desplazamiento_s=corrida * 10_000_000,
                                silencioso=True)
            pps = st["ok"] / st["segundos"] if st["segundos"] else 0
            print("%-12d %-12d %12d %10.2f %12.0f %10d"
                  % (tamano, conc, st["ok"], st["segundos"], pps,
                     st["reintentos"]), flush=True)
            resultados.append({"tamano_lote": tamano, "concurrencia": conc,
                               "lineas_ok": st["ok"],
                               "segundos": round(st["segundos"], 3),
                               "puntos_por_s": round(pps),
                               "reintentos": st["reintentos"]})
    return resultados


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--perfil", default="local")
    ap.add_argument("--entrada", help="directorio con los .lp (por defecto "
                                      "data/generado/<perfil>)")
    ap.add_argument("--db", default=DB_VIVO)
    ap.add_argument("--tamano-lote", type=int, default=5000)
    ap.add_argument("--concurrencia", type=int, default=4)
    ap.add_argument("--reintentos", type=int, default=5)
    ap.add_argument("--tablas", nargs="*", default=TABLAS)
    ap.add_argument("--desorden", action="store_true",
                    help="baraja las lineas dentro de cada lote")
    ap.add_argument("--medir-lotes", action="store_true",
                    help="compara tamanos de lote/concurrencia (base lab)")
    ap.add_argument("--max-lineas-medicion", type=int, default=100000)
    a = ap.parse_args()

    base = Path(a.entrada) if a.entrada else RAIZ / "data" / "generado" / a.perfil
    token = leer_token()
    if not base.exists():
        sys.exit("No existe %s. Ejecutar antes generacion_puntos.py." % base)
    verificar_servidor(token)

    if a.medir_lotes:
        res = medir_lotes(token, base, a.max_lineas_medicion)
        with open(base / "medicion_lotes.json", "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)
        return

    rechazados = base / "rechazados.lp"
    if rechazados.exists():
        rechazados.unlink()
    print("Carga -> base: %s | precision: %s | lote: %d | concurrencia: %d "
          "| desorden: %s" % (a.db, PRECISION, a.tamano_lote, a.concurrencia,
                              "si" if a.desorden else "no"))
    total = {"lineas": 0, "ok": 0, "lotes": 0, "lotes_fallidos": 0,
             "reintentos": 0}
    por_tabla = {}
    t0 = time.time()
    for tabla in a.tablas:
        ruta = base / (tabla + ".lp")
        if not ruta.exists():
            sys.exit("Falta %s" % ruta)
        st = cargar_archivo(token, a.db, ruta, a.tamano_lote, a.concurrencia,
                            a.reintentos, a.desorden, rechazados)
        por_tabla[tabla] = st
        for k in total:
            total[k] += st[k]
        print("  %-22s enviadas=%9d  ok=%9d  lotes=%5d  fallidos=%d  "
              "reintentos=%d  %.1f s  (%.0f puntos/s)"
              % (tabla, st["lineas"], st["ok"], st["lotes"],
                 st["lotes_fallidos"], st["reintentos"], st["segundos"],
                 st["ok"] / st["segundos"] if st["segundos"] else 0))
    seg = time.time() - t0
    print("TOTAL: enviadas=%d ok=%d lotes=%d fallidos=%d reintentos=%d "
          "en %.1f s -> %.0f puntos/s (cliente Python, %d hilos, lote %d)"
          % (total["lineas"], total["ok"], total["lotes"],
             total["lotes_fallidos"], total["reintentos"], seg,
             total["ok"] / seg if seg else 0, a.concurrencia, a.tamano_lote))
    with open(base / "resumen_carga.json", "w", encoding="utf-8") as f:
        json.dump({"base": a.db, "tamano_lote": a.tamano_lote,
                   "concurrencia": a.concurrencia, "desorden": a.desorden,
                   "segundos": round(seg, 2), "total": total,
                   "por_tabla": {t: {k: (round(v, 2) if isinstance(v, float) else v)
                                     for k, v in s.items()}
                                 for t, s in por_tabla.items()}}, f, indent=1)
    if total["lotes_fallidos"]:
        print("ATENCION: hubo lotes rechazados; ver %s" % rechazados)
        sys.exit(1)


if __name__ == "__main__":
    main()
