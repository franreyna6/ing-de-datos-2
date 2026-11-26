"""Diagnostico de los contenedores de las bases (para investigar un target DOWN).

Para cada contenedor de los Hitos 4 a 9 registra: estado, salud, reinicios,
puertos publicados, montajes y las ultimas lineas de su log. Sirve cuando una
base figura como caida en el tablero y hay que saber por que (README, seccion
"Investigar un target DOWN"). No modifica nada.

Salida: evidencia/resultados_sin_secretos/diagnostico_<fecha>.txt (enmascarado).

Uso:
  python scripts/diagnosticar_bases.py
  python scripts/diagnosticar_bases.py --lineas 120
"""
from __future__ import annotations

import argparse
import sys

from lib_monitoreo import (CONTENEDORES, DIR_RESULTADOS, MODULOS_BASES, ahora_utc, docker,
                           escribir_texto, info, iso, paso)

FORMATO = ("estado={{.State.Status}} corriendo={{.State.Running}} "
           "salud={{if .State.Health}}{{.State.Health.Status}}{{else}}sin-healthcheck{{end}} "
           "reinicios={{.RestartCount}} iniciado={{.State.StartedAt}} "
           "exit={{.State.ExitCode}} error={{.State.Error}}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lineas", type=int, default=60)
    a = ap.parse_args(argv)
    momento = ahora_utc()
    salida = [f"# Diagnostico de bases - {iso(momento)}", ""]
    r = docker("ps", "-a", "--filter", "name=fixture2030",
               "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}", timeout=30)
    salida += ["## docker ps -a (fixture2030*)", r.stdout.strip() or r.stderr.strip(), ""]
    for m in MODULOS_BASES:
        nombre = CONTENEDORES[m]
        paso(f"{m}: {nombre}")
        estado = docker("inspect", "-f", FORMATO, nombre, timeout=30)
        montajes = docker("inspect", "-f",
                          "{{range .Mounts}}{{.Type}}:{{.Name}}{{.Source}} -> {{.Destination}}; {{end}}",
                          nombre, timeout=30)
        puertos = docker("port", nombre, timeout=30)
        logs = docker("logs", "--tail", str(a.lineas), nombre, timeout=60)
        info(estado.stdout.strip() or estado.stderr.strip())
        salida += [f"## {m} ({nombre})",
                   f"inspect: {estado.stdout.strip() or estado.stderr.strip()}",
                   f"montajes: {montajes.stdout.strip()}",
                   f"puertos: {puertos.stdout.strip() or '(ninguno publicado)'}",
                   f"--- ultimas {a.lineas} lineas del log ---",
                   (logs.stdout + logs.stderr).strip(), ""]
    destino = DIR_RESULTADOS / f"diagnostico_{momento.strftime('%Y%m%d-%H%M%S')}.txt"
    escribir_texto(destino, "\n".join(salida) + "\n")
    paso(f"Diagnostico guardado en monitoreo/evidencia/resultados_sin_secretos/{destino.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
