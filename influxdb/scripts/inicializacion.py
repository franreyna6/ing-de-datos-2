#!/usr/bin/env python3
"""Inicializacion del ambiente del Hito 8 (RF1, RNF2, RNF3, RNF10).

Pasos (todo con las herramientas del contenedor oficial de InfluxDB 3 Core):
  1. crea ~/docker/data/influxdb (persistencia local);
  2. docker compose up -d;
  3. espera al servidor y registra version, imagen y recursos de Docker;
  4. crea el token de administracion LOCAL con autorizacion_local.py (se
     guarda en .influxdb3-token, archivo EXCLUIDO del repositorio);
  5. crea las bases logicas (retencion fijada al crearlas):
       fixture2030_vivo  retencion 30d  (puntos originales)
       fixture2030_hist  sin expiracion (resumenes de 1 minuto)
       fixture2030_lab   sin expiracion (pruebas descartables)
  6. lista las bases (influxdb3 show databases).

Es idempotente: repetirlo no duplica nada. El token NUNCA se imprime.

Uso: python scripts/inicializacion.py [--sin-compose]
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_influx import (CONTENEDOR, DB_VIVO, DB_HIST, DB_LAB,  # noqa: E402
                        ejecutar, esperar_servidor, influxdb3)
from autorizacion_local import asegurar_token  # noqa: E402

BASES = [(DB_VIVO, "30d"), (DB_HIST, None), (DB_LAB, None)]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--sin-compose", action="store_true",
                    help="no ejecutar docker compose up -d")
    a = ap.parse_args()

    home = Path(os.environ.get("HOME") or Path.home())
    datos = home / "docker" / "data" / "influxdb"
    datos.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(datos, 0o777)       # la imagen 3 Core debe poder escribir
    except OSError:
        pass
    print("[1] Persistencia local: %s" % datos)

    entorno = dict(os.environ)
    entorno.setdefault("HOME", str(home))     # lo usa docker-compose.yml
    if not a.sin_compose:
        print("[2] docker compose up -d (imagen influxdb:3-core, pull always)")
        ejecutar(["docker", "compose", "up", "-d"], entorno)
        print(ejecutar(["docker", "compose", "ps"], entorno).stdout.strip())

    print("[3] Esperando al servidor en el puerto 8181 ...")
    if not esperar_servidor():
        sys.exit("El servidor no respondio. Ver: docker compose logs influxdb")
    print("    version del servidor : "
          + influxdb3(["--version"]).stdout.strip())
    img = ejecutar(["docker", "inspect", CONTENEDOR, "--format",
                    "{{.Config.Image}} id={{.Image}}"]).stdout.strip()
    print("    imagen               : " + img)
    info = ejecutar(["docker", "info", "--format",
                     "CPUs={{.NCPU}} memoria_bytes={{.MemTotal}} SO={{.OperatingSystem}}"],
                    ok_si_falla=True).stdout.strip()
    print("    recursos de Docker   : " + info)

    print("[4] Token de administracion local (autorizacion_local.py)")
    token = asegurar_token()

    print("[5] Bases de datos (la retencion se fija al crearlas y no se modifica)")
    for nombre, retencion in BASES:
        args = ["create", "database", nombre]
        if retencion:
            args += ["--retention-period", retencion]
        r = influxdb3(args, token, ok_si_falla=True)
        salida = (r.stdout + r.stderr).lower()
        if r.returncode == 0:
            estado = "creada"
        elif "already exists" in salida:
            estado = "ya existia"
        else:
            sys.exit("No se pudo crear %s: %s" % (nombre, (r.stderr or r.stdout)[:300]))
        print("    %-18s retencion=%-4s %s" % (nombre, retencion or "sin limite", estado))

    print("[6] influxdb3 show databases")
    print("    " + influxdb3(["show", "databases"], token).stdout.strip()
          .replace("\n", "\n    "))
    print("Ambiente listo.")


if __name__ == "__main__":
    main()
