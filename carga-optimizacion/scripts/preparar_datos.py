"""PREPARACION: genera el plan de operaciones de la prueba (RF3).

El "dataset" de esta prueba es la secuencia de operaciones que los usuarios
virtuales van a ejecutar contra la API: que lectura o escritura, sobre que
partido, con que usuario, contenido y comentarioId. Se genera con una SEMILLA
fija (config/escenario.json), asi que dos ejecuciones producen exactamente el
mismo archivo (se verifica con su hash SHA-256).

Salidas:
  datos/plan.jsonl          una operacion por linea (no se versiona: se regenera)
  datos/resumen_plan.json   distribucion real del plan + hash (se versiona)

Uso:
  python scripts/preparar_datos.py
"""
from __future__ import annotations

import collections
import random
import uuid

from lib_carga import (ARCHIVO_PLAN, ARCHIVO_RESUMEN_PLAN,
                       cargar_escenario, escribir_json, sha256_archivo,
                       sha256_escenario)

FRASES = [
    "Que golazo, no lo puedo creer",
    "El arquero no tuvo ninguna chance",
    "Hay que cerrar el partido ya",
    "Ese pase previo fue de otro planeta",
    "El VAR va a revisar la jugada?",
    "Partidazo, esto es el Mundial",
    "Ahora tienen que salir a buscar el empate",
    "La defensa quedo mal parada",
    "Que celebracion en la tribuna",
    "Cambio urgente en el mediocampo",
]


def generar_plan(esc: dict) -> list[dict]:
    rng = random.Random(esc["semilla"])
    mezcla = esc["mezcla"]
    claves = [p["clave"] for p in esc["partidos"]]
    pesos = [p["peso"] for p in esc["partidos"]]
    ops, escrituras_recientes = [], []
    for i in range(esc["operaciones_en_el_plan"]):
        r = rng.random()
        if r < mezcla["lectura"]:
            tipo = "lectura"
        elif r < mezcla["lectura"] + mezcla["escritura"] or not escrituras_recientes:
            tipo = "escritura"
        else:
            tipo = "reintento"

        if tipo == "lectura":
            ops.append({"i": i, "tipo": tipo,
                        "partido": rng.choices(claves, pesos)[0]})
        elif tipo == "escritura":
            op = {
                "i": i, "tipo": tipo,
                "partido": rng.choices(claves, pesos)[0],
                "usuarioId": f"u-{rng.randint(1, esc['usuarios_distintos']):05d}",
                # El sufijo #i hace unico cada contenido: permite detectar si
                # un comentario se guardo alterado o mezclado con otro.
                "contenido": f"{rng.choice(FRASES)} #{i}",
                "comentarioId": str(uuid.UUID(int=rng.getrandbits(128), version=4)),
            }
            ops.append(op)
            escrituras_recientes.append(op)
            escrituras_recientes = escrituras_recientes[-200:]
        else:
            # Reintento de cliente: reenvia EXACTAMENTE el mismo comentario
            # (mismo comentarioId, la "clave de idempotencia" del Hito 10) de
            # una escritura reciente, como haria una app movil tras un timeout.
            orig = rng.choice(escrituras_recientes)
            ops.append({"i": i, "tipo": tipo, "partido": orig["partido"],
                        "usuarioId": orig["usuarioId"], "contenido": orig["contenido"],
                        "comentarioId": orig["comentarioId"], "reintentoDe": orig["i"]})
    return ops


def main() -> None:
    esc = cargar_escenario()
    ops = generar_plan(esc)
    ARCHIVO_PLAN.parent.mkdir(parents=True, exist_ok=True)
    import json
    with open(ARCHIVO_PLAN, "w", encoding="utf-8", newline="\n") as f:
        for op in ops:
            f.write(json.dumps(op, ensure_ascii=False) + "\n")

    por_tipo = collections.Counter(o["tipo"] for o in ops)
    por_partido = collections.Counter(o["partido"] for o in ops)
    usuarios = {o["usuarioId"] for o in ops if "usuarioId" in o}
    ids = [o["comentarioId"] for o in ops if o["tipo"] == "escritura"]
    resumen = {
        "semilla": esc["semilla"],
        "escenario_sha256": sha256_escenario(),
        "plan_sha256": sha256_archivo(ARCHIVO_PLAN),
        "operaciones": len(ops),
        "por_tipo": dict(por_tipo),
        "por_partido": dict(por_partido),
        "usuarios_distintos_usados": len(usuarios),
        "comentario_ids_unicos_en_escrituras": len(set(ids)),
        "escrituras": len(ids),
        "nota": "El plan es mas largo que lo que consume una corrida: cada corrida usa "
                "las primeras N operaciones, en orden. Lo consumido queda en "
                "docs/evidencia/<corrida>/operaciones.csv.gz.",
    }
    escribir_json(ARCHIVO_RESUMEN_PLAN, resumen)
    print(f"Plan generado: {len(ops)} operaciones -> {ARCHIVO_PLAN}")
    print(f"  por tipo:    {dict(por_tipo)}")
    print(f"  por partido: {dict(por_partido)}")
    print(f"  sha256:      {resumen['plan_sha256']}")
    if len(set(ids)) != len(ids):
        raise SystemExit("ERROR: el plan tiene comentarioId repetidos en escrituras nuevas")


if __name__ == "__main__":
    main()
