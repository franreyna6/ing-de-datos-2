#!/usr/bin/env python3
"""Agregaciones del Hito 8 (RF9, RF10).

1) Ejecuta scripts/sql/agregaciones.sql sobre fixture2030_vivo. Cada bloque
   declara la funcion usada y la semantica de la medida que la justifica.
2) Materializa el RESUMEN DE 1 MINUTO de estadisticas_equipo en la tabla
   estadisticas_equipo_1m de la base fixture2030_hist (downsampling):
     posesion_pct   -> AVG por minuto        (muestra instantanea)
     pases/tiros/recuperaciones acumulados -> MAX por minuto (cierre del minuto)
     muestras       -> COUNT(*) (puntos originales resumidos en cada ventana)
   Es idempotente: repetirlo reemplaza los mismos puntos (misma serie y
   timestamp). Ver docs/retencion_y_granularidad.md.

Uso:
  python scripts/agregaciones.py                # SQL + resumen
  python scripts/agregaciones.py --solo-sql
  python scripts/agregaciones.py --solo-resumen
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_influx import (RAIZ, DB_VIVO, DB_HIST, Sesion, ejecutar_bloques,  # noqa: E402
                        epoch_desde_iso, tabla_texto)

SQL_RESUMEN = """
SELECT date_trunc('minute', time) AS minuto, partido_id, equipo_id, sede, grupo,
       AVG(posesion_pct) AS posesion_pct_prom,
       MAX(pases_acum) AS pases_acum_max,
       MAX(tiros_acum) AS tiros_acum_max,
       MAX(recuperaciones_acum) AS recuperaciones_acum_max,
       COUNT(*) AS muestras
FROM estadisticas_equipo
WHERE time >= '2030-06-01T00:00:00Z' AND time < '2030-07-15T00:00:00Z'
GROUP BY date_trunc('minute', time), partido_id, equipo_id, sede, grupo
ORDER BY minuto, partido_id, equipo_id
""".strip()


def materializar_resumen():
    sesion = Sesion()
    print("=" * 78)
    print("R1 | Resumen de 1 minuto: estadisticas_equipo -> estadisticas_equipo_1m")
    print("  origen: %s | destino: %s" % (DB_VIVO, DB_HIST))
    filas = sesion.consultar(DB_VIVO, SQL_RESUMEN)
    print("  ventanas de 1 minuto calculadas: %d" % len(filas))
    lineas = []
    for f in filas:
        ts = epoch_desde_iso(f["minuto"])
        lineas.append(
            "estadisticas_equipo_1m,partido_id=%s,equipo_id=%s,sede=%s,grupo=%s "
            "posesion_pct_prom=%.2f,pases_acum_max=%di,tiros_acum_max=%di,"
            "recuperaciones_acum_max=%di,muestras=%di %d"
            % (f["partido_id"], f["equipo_id"], f["sede"], f["grupo"],
               float(f["posesion_pct_prom"]), int(f["pases_acum_max"]),
               int(f["tiros_acum_max"]), int(f["recuperaciones_acum_max"]),
               int(f["muestras"]), ts))
    escritas = 0
    for i in range(0, len(lineas), 5000):
        lote = lineas[i:i + 5000]
        estado, texto = sesion.escribir(DB_HIST, "\n".join(lote) + "\n")
        if estado not in (200, 204):
            sys.exit("Error al escribir el resumen: HTTP %d %s" % (estado, texto[:300]))
        escritas += len(lote)
    print("  puntos escritos en %s: %d (precision: segundos)" % (DB_HIST, escritas))
    # Comprobaciones del resumen: cuenta y relacion con los puntos originales.
    n_hist = sesion.consultar(
        DB_HIST, "SELECT COUNT(*) AS n, SUM(muestras) AS puntos_resumidos "
                 "FROM estadisticas_equipo_1m")[0]
    n_orig = sesion.consultar(
        DB_VIVO, "SELECT COUNT(*) AS n FROM estadisticas_equipo "
                 "WHERE time >= '2030-06-01T00:00:00Z' AND time < '2030-07-15T00:00:00Z'")[0]
    print("  comprobacion: ventanas en hist=%s | puntos originales resumidos=%s "
          "| puntos originales en vivo=%s"
          % (n_hist["n"], n_hist["puntos_resumidos"], n_orig["n"]))
    ok = int(n_hist["puntos_resumidos"]) == int(n_orig["n"])
    print("  RESULTADO: %s" % ("OK, el resumen cubre todos los puntos originales"
                               if ok else "DIFERENCIA, revisar"))
    muestra = sesion.consultar(
        DB_HIST, "SELECT time, equipo_id, posesion_pct_prom, tiros_acum_max, muestras "
                 "FROM estadisticas_equipo_1m WHERE partido_id = 'F2030-018' "
                 "AND time >= '2030-06-13T09:00:00Z' AND time < '2030-06-13T09:03:00Z' "
                 "ORDER BY time, equipo_id")
    print("  ejemplo (partido de referencia, minutos 60 a 63):")
    print("\n".join("    " + l for l in tabla_texto(muestra, 8).splitlines()))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--solo-sql", action="store_true")
    ap.add_argument("--solo-resumen", action="store_true")
    a = ap.parse_args()
    codigo = 0
    if not a.solo_resumen:
        codigo |= 1 if ejecutar_bloques(
            RAIZ / "scripts" / "sql" / "agregaciones.sql", DB_VIVO) else 0
    if not a.solo_sql:
        codigo |= materializar_resumen()
    sys.exit(codigo)


if __name__ == "__main__":
    main()
