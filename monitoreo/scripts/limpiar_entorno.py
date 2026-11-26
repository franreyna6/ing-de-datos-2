"""Detiene el monitoreo y, opcionalmente, limpia datos de prueba (RNF11: no destructivo).

Por defecto solo hace "docker compose down" de monitoreo/: los contenedores de
monitoreo se quitan, pero los volumenes (historial de Prometheus y Grafana) y
TODAS las bases quedan intactos.

Opciones:
  --borrar-datos-monitoreo   tambien borra los volumenes del monitoreo
                             (fixture2030_prometheus_datos y fixture2030_grafana_datos).
                             Nunca toca volumenes de las bases.
  --detener-bases            docker stop de los contenedores de los Hitos 4 a 9
                             (no los borra; se vuelven a iniciar con docker start).
  --datos-de-prueba ETIQUETA borra lo que escribio una corrida de la prueba:
                             las particiones (partido_id, ventana) de los partidos
                             de laboratorio H13-ETIQUETA-P1/P2 en Cassandra y sus
                             claves de cache en Redis. Sin --confirmar solo muestra
                             lo que borraria.

Uso:
  python scripts/limpiar_entorno.py
  python scripts/limpiar_entorno.py --datos-de-prueba 20261126-031500 --confirmar
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

from lib_monitoreo import (CONTENEDORES, DIR_EVIDENCIA, MODULOS_BASES, RAIZ, aviso, docker,
                           info, leer_json, paso)

KEYSPACE, TABLA = "fixture2030_comentarios", "comentarios_por_partido"


def limpiar_datos_de_prueba(etiqueta: str, confirmar: bool) -> int:
    meta_path = DIR_EVIDENCIA / "prueba_de_falla" / etiqueta / "metadata.json"
    if not meta_path.exists():
        aviso(f"No existe {meta_path}")
        return 1
    meta = leer_json(meta_path)
    sentencias = []
    for partido, ventana in meta.get("ventanas_escritas", []):
        if not partido.startswith("H13-"):
            continue  # nunca un partido real del fixture
        # La API devuelve la ventana en ISO-8601; cqlsh la recibe como en el Hito 12.
        v = dt.datetime.fromisoformat(ventana.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
        sentencias.append(f"DELETE FROM {TABLA} WHERE partido_id = '{partido}' "
                          f"AND ventana = '{v.strftime('%Y-%m-%d %H:%M:%S+0000')}';")
    paso(f"Datos de prueba de {etiqueta}: {len(sentencias)} particiones de laboratorio en Cassandra")
    for s in sentencias:
        info(s)
    patron = f"cache:comentarios:H13-{etiqueta}-*"
    r = docker("exec", CONTENEDORES["redis"], "redis-cli", "--scan", "--pattern", patron, timeout=60)
    claves = [c for c in r.stdout.split() if c.startswith("cache:comentarios:H13-")]
    info(f"Redis: {len(claves)} claves de cache con el patron {patron}")
    if not confirmar:
        info("Simulacion: no se borro nada. Agregar --confirmar para borrar.")
        return 0
    for s in sentencias:
        r = docker("exec", CONTENEDORES["cassandra"], "cqlsh", "-k", KEYSPACE, "-e", s, timeout=120)
        if r.returncode != 0:
            aviso(r.stderr.strip()[:200])
    if claves:
        docker("exec", CONTENEDORES["redis"], "redis-cli", "DEL", *claves, timeout=60)
    info("Datos de prueba borrados. La evidencia de la corrida se conserva.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--borrar-datos-monitoreo", action="store_true")
    ap.add_argument("--detener-bases", action="store_true")
    ap.add_argument("--datos-de-prueba", metavar="ETIQUETA")
    ap.add_argument("--confirmar", action="store_true")
    ap.add_argument("--mantener-monitoreo", action="store_true",
                    help="no hacer docker compose down (por ejemplo, para solo limpiar datos de prueba)")
    a = ap.parse_args(argv)
    if a.datos_de_prueba:
        limpiar_datos_de_prueba(a.datos_de_prueba, a.confirmar)
    if not a.mantener_monitoreo:
        paso("Deteniendo el monitoreo (docker compose down" + (" -v" if a.borrar_datos_monitoreo else "") + ")")
        args = ["compose", "down"] + (["-v"] if a.borrar_datos_monitoreo else [])
        r = docker(*args, timeout=300, cwd=RAIZ)
        info("ok" if r.returncode == 0 else r.stderr.strip()[-300:])
    if a.detener_bases:
        paso("Deteniendo las bases (docker stop, sin borrar contenedores ni volumenes)")
        for m in MODULOS_BASES:
            r = docker("stop", CONTENEDORES[m], timeout=180)
            info(f"{CONTENEDORES[m]}: {'detenido' if r.returncode == 0 else r.stderr.strip()[:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
