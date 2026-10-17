#!/usr/bin/env python3
"""Limpieza OPCIONAL del Hito 8 (RNF9). No forma parte del flujo normal.

  --generados   borra data/generado/ (se regenera con la misma semilla)
  --ambiente    docker compose down (detiene y quita el contenedor; los datos
                en ~/docker/data/influxdb se CONSERVAN)
  --datos --si  ademas BORRA ~/docker/data/influxdb y el token local; se
                vuelve a empezar de cero. Exige --si para confirmar.

Uso: python scripts/limpieza.py --generados
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_influx import RAIZ, ARCHIVO_TOKEN, ejecutar  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--generados", action="store_true")
    ap.add_argument("--ambiente", action="store_true")
    ap.add_argument("--datos", action="store_true")
    ap.add_argument("--si", action="store_true", help="confirma el borrado")
    a = ap.parse_args()
    if not (a.generados or a.ambiente or a.datos):
        ap.print_help()
        return
    entorno = dict(os.environ)
    entorno.setdefault("HOME", str(Path.home()))
    if a.generados:
        shutil.rmtree(RAIZ / "data" / "generado", ignore_errors=True)
        print("data/generado/ borrado")
    if a.ambiente or a.datos:
        ejecutar(["docker", "compose", "down"], entorno, ok_si_falla=True)
        print("contenedor detenido y quitado (docker compose down)")
    if a.datos:
        if not a.si:
            sys.exit("Esto borra TODOS los datos de InfluxDB. Repetir con --si")
        datos = Path(entorno["HOME"]) / "docker" / "data" / "influxdb"
        shutil.rmtree(datos, ignore_errors=True)
        if ARCHIVO_TOKEN.exists():
            ARCHIVO_TOKEN.unlink()
        print("%s y el token local borrados" % datos)


if __name__ == "__main__":
    main()
