"""LIMPIEZA OPCIONAL de los datos de UNA corrida (RNF11: no destructivo).

Borra solamente lo que escribio esa corrida:
  - en Cassandra, las particiones (partido_id, ventana) de los partidos de
    laboratorio 'H12-<etiqueta>-P*' (ningun partido real del fixture);
  - en Redis, las claves 'cache:comentarios:H12-<etiqueta>-*' que sigan vivas.
No toca volumenes, contenedores, otras tablas, sesiones ni la evidencia en
docs/evidencia/ (los resultados medidos se conservan).

Por defecto solo MUESTRA lo que borraria. Para borrar de verdad: --confirmar.
Limpiar NO es necesario para repetir la prueba: cada corrida usa partidos
propios, asi que las corridas no se pisan entre si.

Uso:
  python scripts/limpiar_datos_de_prueba.py <etiqueta>               # simulacion
  python scripts/limpiar_datos_de_prueba.py <etiqueta> --confirmar   # borra
"""
from __future__ import annotations

import datetime as dt
import sys

from lib_carga import (DIR_EVIDENCIA, cargar_config, cqlsh, leer_json, redis_cli,
                       ventanas_entre)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    confirmar = "--confirmar" in sys.argv
    if len(args) != 1:
        raise SystemExit("Uso: python scripts/limpiar_datos_de_prueba.py <etiqueta> [--confirmar]")
    etiqueta = args[0]
    meta = leer_json(DIR_EVIDENCIA / etiqueta / "metadata.json")
    cfg = cargar_config()
    inicio = dt.datetime.fromisoformat(meta["inicio_utc"])
    fin = dt.datetime.fromisoformat(meta["fin_utc"]) + dt.timedelta(seconds=10)

    sentencias = []
    for partido in meta["partidos_de_la_corrida"].values():
        if not partido.startswith("H12-"):
            raise SystemExit(f"Partido inesperado '{partido}': se aborta por seguridad.")
        for v in ventanas_entre(inicio, fin):
            sentencias.append(
                "DELETE FROM comentarios_por_partido WHERE partido_id = "
                f"'{partido}' AND ventana = '{v.strftime('%Y-%m-%d %H:%M:%S+0000')}';")
    claves = [c for c in redis_cli(cfg, "--scan", "--pattern",
                                   f"cache:comentarios:H12-{etiqueta}-*").splitlines() if c.strip()]

    print(f"Corrida {etiqueta}: {len(sentencias)} particiones de Cassandra y "
          f"{len(claves)} claves de Redis.")
    for s in sentencias:
        print("  " + s)
    for c in claves:
        print("  DEL " + c)
    if not confirmar:
        print("\nSimulacion: no se borro nada. Agregar --confirmar para borrar.")
        return
    for s in sentencias:
        cqlsh(cfg, s)
    if claves:
        redis_cli(cfg, "DEL", *claves)
    print("Listo. La evidencia en docs/evidencia/ se conserva.")


if __name__ == "__main__":
    main()
