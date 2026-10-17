#!/usr/bin/env python3
"""Consultas temporales del Hito 8: ventana, filtro por dimensiones y
comparacion entre dimensiones (RF8). Las sentencias estan en
scripts/sql/consultas_temporales.sql; este script las ejecuta una por una
contra fixture2030_vivo y muestra resultado y tiempo.

Los tiempos son de UNA ejecucion en la maquina local y no constituyen una
medicion de rendimiento (ver docs/pruebas_y_evidencia.md).

Uso: python scripts/consultas_temporales.py [C1 C4 ...]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_influx import RAIZ, DB_VIVO, ejecutar_bloques  # noqa: E402

if __name__ == "__main__":
    fallos = ejecutar_bloques(RAIZ / "scripts" / "sql" / "consultas_temporales.sql",
                              DB_VIVO, solo=sys.argv[1:] or None)
    sys.exit(1 if fallos else 0)
