#!/usr/bin/env python3
"""Prueba de persistencia del Hito 8 (RNF2).

Demuestra que los datos sobreviven al reinicio del contenedor:
  1. cuenta los puntos de cada tabla (base vivo y resumen en hist);
  2. ejecuta `docker compose restart`;
  3. espera al servidor, vuelve a contar y compara.
Tambien informa el tamano en disco de ~/docker/data/influxdb.
Codigo de salida 1 si algun conteo cambia.

Uso: python scripts/persistencia.py
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_influx import (DB_HIST, DB_VIVO, Sesion, ejecutar,  # noqa: E402
                        esperar_servidor)

TABLAS_VIVO = ["estadisticas_equipo", "actividad_usuarios",
               "metricas_plataforma", "estadisticas_jugador"]
RANGO = "time >= '2030-06-01T00:00:00Z' AND time < '2030-07-15T00:00:00Z'"


def contar():
    s = Sesion()
    resultado = {}
    destinos = [("vivo." + t, DB_VIVO, t) for t in TABLAS_VIVO]
    destinos.append(("hist.estadisticas_equipo_1m", DB_HIST,
                     "estadisticas_equipo_1m"))
    for nombre, db, tabla in destinos:
        try:
            resultado[nombre] = int(s.consultar(
                db, "SELECT COUNT(*) AS n FROM %s WHERE %s" % (tabla, RANGO))[0]["n"])
        except RuntimeError:
            resultado[nombre] = 0          # la tabla todavia no existe
    return resultado


def tamano_mb(ruta):
    if not ruta.exists():
        return 0.0
    return sum(f.stat().st_size for f in ruta.rglob("*") if f.is_file()) / 1048576


def main():
    home = Path(os.environ.get("HOME") or Path.home())
    datos = home / "docker" / "data" / "influxdb"
    entorno = dict(os.environ)
    entorno.setdefault("HOME", str(home))

    antes = contar()
    print("Antes del reinicio:  " + ", ".join("%s=%d" % kv for kv in antes.items()))
    print("Tamano en disco de %s: %.1f MB" % (datos, tamano_mb(datos)))
    print("docker compose restart ...")
    ejecutar(["docker", "compose", "restart"], entorno)
    if not esperar_servidor(120):
        sys.exit("El servidor no volvio a responder tras el reinicio.")

    despues, ultimo = None, ""
    for _ in range(10):                      # el catalogo puede tardar unos segundos
        try:
            despues = contar()
            break
        except Exception as exc:             # servidor todavia arrancando
            ultimo = str(exc)
            time.sleep(3)
    if despues is None:
        sys.exit("No se pudo consultar tras el reinicio: " + ultimo[:200])

    print("%-30s %12s %12s  resultado" % ("tabla", "antes", "despues"))
    fallo = False
    for k, v in antes.items():
        ok = despues.get(k) == v
        fallo |= not ok
        print("%-30s %12d %12d  %s" % (k, v, despues.get(k, -1), "PASS" if ok else "FAIL"))
    if sum(antes.values()) == 0:
        print("AVISO: no habia datos cargados antes del reinicio; la prueba no es concluyente.")
        fallo = True
    print("Persistencia: %s" % ("FAIL, los conteos cambiaron" if fallo else
                                "PASS, los datos sobrevivieron al reinicio"))
    sys.exit(1 if fallo else 0)


if __name__ == "__main__":
    main()
