#!/usr/bin/env python3
"""Limpieza opcional del Hito 11 (RNF15).

Borra SOLO archivos locales que genera la evaluacion y que no se versionan:
  - docs/evidencia/logs/crudos/   logs de la API sin redactar
  - scripts/__pycache__/
Con --corridas tambien borra docs/evidencia/corridas/ (se regeneran al evaluar).

No toca ningun producto, contenedor, volumen, base ni dato del dominio, y no
borra la configuracion local (config/configuracion.env).

Uso: python limpieza.py [--corridas] [--si]
"""
from __future__ import annotations

import argparse
import shutil

from lib_conectividad import DIR_EVIDENCIA, RAIZ_MODULO


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corridas", action="store_true", help="incluir docs/evidencia/corridas/")
    ap.add_argument("--si", action="store_true", help="confirmar (sin esto solo lista)")
    a = ap.parse_args()
    objetivos = [DIR_EVIDENCIA / "logs" / "crudos", RAIZ_MODULO / "scripts" / "__pycache__"]
    if a.corridas:
        objetivos.append(DIR_EVIDENCIA / "corridas")
    for d in objetivos:
        if not d.exists():
            continue
        if a.si:
            shutil.rmtree(d)
            print(f"borrado: {d.relative_to(RAIZ_MODULO)}")
        else:
            print(f"se borraria: {d.relative_to(RAIZ_MODULO)} (agregar --si para confirmar)")


if __name__ == "__main__":
    main()
