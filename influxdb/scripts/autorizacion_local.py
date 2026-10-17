#!/usr/bin/env python3
"""Autorizacion local del Hito 8 (RNF3, RNF7, RNF9).

InfluxDB 3 Core exige un token. Este script lo crea la primera vez con
`influxdb3 create token --admin` (herramienta del contenedor) y lo guarda en
.influxdb3-token, archivo EXCLUIDO del repositorio. El token no se muestra
nunca, porque el servidor solo lo entrega al crearlo.

Es idempotente: si el archivo ya existe, lo reutiliza.
Uso: python scripts/autorizacion_local.py
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_influx import ARCHIVO_TOKEN, influxdb3  # noqa: E402


def asegurar_token():
    """Devuelve el token local, creandolo si hace falta."""
    if ARCHIVO_TOKEN.exists():
        print("    se reutiliza %s (excluido de Git)" % ARCHIVO_TOKEN.name)
        return ARCHIVO_TOKEN.read_text(encoding="utf-8").strip()
    r = influxdb3(["create", "token", "--admin"], ok_si_falla=True)
    m = re.search(r"apiv3_[A-Za-z0-9_\-]+", r.stdout + r.stderr)
    if r.returncode != 0 or not m:
        sys.exit(
            "No se pudo crear el token (%s).\nSi el servidor ya tiene un token "
            "de una corrida anterior y se perdio %s, hay que reiniciar los "
            "datos: python scripts/limpieza.py --datos --si"
            % ((r.stderr or r.stdout).strip()[:200], ARCHIVO_TOKEN.name))
    token = m.group(0)
    ARCHIVO_TOKEN.write_text(token + "\n", encoding="utf-8")
    try:
        os.chmod(ARCHIVO_TOKEN, 0o600)
    except OSError:
        pass
    print("    token creado y guardado en %s (no se muestra)" % ARCHIVO_TOKEN.name)
    return token


if __name__ == "__main__":
    asegurar_token()
