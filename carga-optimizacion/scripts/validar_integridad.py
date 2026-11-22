"""VALIDACION: comprueba que los datos de una corrida no se perdieron, duplicaron
ni alteraron (RF15, RNF4). Un 201 de la API NO se toma como prueba suficiente:
se compara lo que el generador envio contra lo que efectivamente quedo en
Cassandra, leyendo con cqlsh (cliente oficial) particion por particion.

Que verifica:
  1. Generadas vs aceptadas vs rechazadas (y la causa de cada rechazo).
  2. Cada comentario aceptado (201) existe en Cassandra -> si no, PERDIDO.
  3. Usuario y contenido guardados son los enviados -> si no, ALTERADO.
  4. Filas con el mismo comentario_id:
       - explicadas por un reintento del plan  -> DUPLICADO POR REINTENTO
       - sin reintento que las explique        -> DUPLICADO INESPERADO
  5. Filas en Cassandra que el cliente no vio confirmadas (p. ej. timeout del
     cliente pero la base si escribio) -> ESCRITO SIN CONFIRMACION.
  6. Conteos por partido y por ventana (particion).
  7. Redis: toda clave de cache de la corrida tiene TTL (ninguna queda sin
     vencimiento) y si hubo expulsiones (evicted_keys) durante la prueba.

Uso:
  python scripts/validar_integridad.py <etiqueta>
Salida: docs/evidencia/<etiqueta>/integridad.json y integridad.md
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import gzip
import io
import json
import sys

from lib_carga import (ARCHIVO_PLAN, DIR_EVIDENCIA, cargar_config, cqlsh,
                       escribir_json, filas_json_cqlsh, leer_json, redis_cli,
                       ventanas_entre)


def leer_operaciones(dir_corrida):
    with gzip.open(dir_corrida / "operaciones.csv.gz", "rt", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python scripts/validar_integridad.py <etiqueta>")
    etiqueta = sys.argv[1]
    dir_corrida = DIR_EVIDENCIA / etiqueta
    meta = leer_json(dir_corrida / "metadata.json")
    cfg = cargar_config()
    ops = leer_operaciones(dir_corrida)

    # Lo que el plan mando a escribir (contenido esperado de cada comentarioId)
    plan = {}
    with open(ARCHIVO_PLAN, encoding="utf-8") as f:
        for linea in f:
            op = json.loads(linea)
            if op["tipo"] == "escritura":
                plan[op["comentarioId"]] = op

    escrituras = [o for o in ops if o["tipo"] in ("escritura", "reintento")]
    lecturas = [o for o in ops if o["tipo"] == "lectura"]
    enviados = collections.Counter(o["comentario_id"] for o in escrituras)
    aceptados = collections.Counter(o["comentario_id"] for o in escrituras if o["ok"] == "1")
    rechazos = collections.Counter(o["error"] for o in escrituras if o["ok"] != "1")

    # Leer de Cassandra TODAS las particiones que la corrida pudo tocar
    inicio = dt.datetime.fromisoformat(meta["inicio_utc"])
    fin = dt.datetime.fromisoformat(meta["fin_utc"]) + dt.timedelta(seconds=10)
    ventanas = ventanas_entre(inicio, fin)
    filas, por_particion = [], {}
    print(f"Leyendo {len(meta['partidos_de_la_corrida']) * len(ventanas)} particiones con cqlsh...")
    for clave, partido in meta["partidos_de_la_corrida"].items():
        if clave == "CHK":
            continue
        for v in ventanas:
            v_cql = v.strftime("%Y-%m-%d %H:%M:%S+0000")
            salida = cqlsh(cfg, "PAGING OFF; SELECT JSON comentario_id, usuario_id, contenido, "
                                "creado_en FROM comentarios_por_partido "
                                f"WHERE partido_id = '{partido}' AND ventana = '{v_cql}';")
            fs = filas_json_cqlsh(salida)
            por_particion[f"{clave} {v.strftime('%H:%M')}"] = len(fs)
            for fila in fs:
                fila["_clave_partido"] = clave
                filas.append(fila)

    en_base = collections.Counter(f["comentario_id"] for f in filas)
    filas_por_id = collections.defaultdict(list)
    for f in filas:
        filas_por_id[f["comentario_id"]].append(f)

    perdidos = [cid for cid in aceptados if cid not in en_base]
    alterados = []
    for cid, fs in filas_por_id.items():
        esperado = plan.get(cid)
        for f in fs:
            if esperado is None or f.get("usuario_id") != esperado["usuarioId"] \
                    or f.get("contenido") != esperado["contenido"]:
                alterados.append(cid)
                break
    dup_reintento, dup_inesperado = {}, {}
    for cid, n in en_base.items():
        if n > 1:
            # Un reintento explica filas extra solo si el cliente envio ese id mas de una vez
            (dup_reintento if enviados.get(cid, 0) >= n else dup_inesperado)[cid] = n
    sin_confirmacion = [cid for cid in en_base if cid not in aceptados]
    reintentos_aceptados = sum(1 for o in escrituras if o["tipo"] == "reintento" and o["ok"] == "1")

    # Redis: claves de cache de la corrida y expulsiones
    redis_chk = {}
    try:
        patron = f"cache:comentarios:H12-{etiqueta}-*"
        claves = [c for c in redis_cli(cfg, "--scan", "--pattern", patron).splitlines() if c.strip()]
        sin_ttl = [c for c in claves if redis_cli(cfg, "TTL", c).strip() == "-1"]
        redis_chk = {
            "claves_de_cache_que_siguen_vivas": len(claves),
            "claves_de_cache_sin_ttl": len(sin_ttl),
            "evicted_keys_durante_la_prueba": meta.get("redis_delta", {}).get("evicted_keys"),
            "claves_sesion_antes_despues": [meta.get("redis_delta", {}).get("claves_sesion_antes"),
                                            meta.get("redis_delta", {}).get("claves_sesion_despues")],
        }
    except Exception as e:
        redis_chk = {"error": f"no se pudo consultar Redis: {e}"}

    lect_incoherentes = sum(1 for o in lecturas if o["error"] == "respuesta_inconsistente")
    resultado = {
        "etiqueta": etiqueta,
        "escrituras_enviadas": len(escrituras),
        "escrituras_aceptadas_201": sum(1 for o in escrituras if o["ok"] == "1"),
        "escrituras_rechazadas": sum(rechazos.values()),
        "rechazos_por_causa": dict(rechazos),
        "reintentos_enviados": sum(1 for o in escrituras if o["tipo"] == "reintento"),
        "reintentos_aceptados": reintentos_aceptados,
        "comentario_ids_unicos_aceptados": len(aceptados),
        "filas_en_cassandra": len(filas),
        "comentario_ids_unicos_en_cassandra": len(en_base),
        "perdidos": len(perdidos),
        "alterados": len(alterados),
        "duplicados_por_reintento": {"ids": len(dup_reintento),
                                     "filas_extra": sum(n - 1 for n in dup_reintento.values())},
        "duplicados_inesperados": {"ids": len(dup_inesperado),
                                   "filas_extra": sum(n - 1 for n in dup_inesperado.values())},
        "escritos_sin_confirmacion": len(sin_confirmacion),
        "lecturas_totales": len(lecturas),
        "lecturas_con_respuesta_incoherente": lect_incoherentes,
        "filas_por_particion": por_particion,
        "redis": redis_chk,
        "muestras": {"perdidos": perdidos[:10], "alterados": alterados[:10],
                     "duplicados_inesperados": list(dup_inesperado)[:10],
                     "sin_confirmacion": sin_confirmacion[:10]},
    }
    # Veredicto: integridad OK si nada se perdio, altero ni duplico sin explicacion.
    problemas = []
    if perdidos:
        problemas.append(f"{len(perdidos)} aceptados no estan en Cassandra")
    if alterados:
        problemas.append(f"{len(alterados)} comentarios alterados")
    if dup_inesperado:
        problemas.append(f"{len(dup_inesperado)} ids duplicados sin reintento que lo explique")
    if lect_incoherentes:
        problemas.append(f"{lect_incoherentes} lecturas incoherentes")
    if redis_chk.get("claves_de_cache_sin_ttl"):
        problemas.append("hay claves de cache sin TTL")
    resultado["veredicto"] = "OK" if not problemas else "CON PROBLEMAS"
    resultado["problemas"] = problemas
    resultado["observaciones"] = []
    if dup_reintento:
        resultado["observaciones"].append(
            f"{len(dup_reintento)} comentarios quedaron con mas de una fila por reintentos del "
            "cliente: la clave de idempotencia (comentarioId) NO evita el duplicado porque "
            "creado_en (asignado por la API en cada request) forma parte de la clave primaria. "
            "Ver docs/integridad_y_limitaciones.md.")
    if sin_confirmacion:
        resultado["observaciones"].append(
            f"{len(sin_confirmacion)} comentarios se guardaron aunque el cliente no recibio el 201 "
            "(timeout o corte de conexion): el cliente los veria como fallidos.")
    md = io.StringIO()
    md.write(f"# Integridad de la corrida `{etiqueta}`\n\n**Veredicto: __VEREDICTO__**\n\n")
    md.write("| Control | Valor |\n|---|---:|\n")
    for k in ["escrituras_enviadas", "escrituras_aceptadas_201", "escrituras_rechazadas",
              "reintentos_enviados", "reintentos_aceptados", "comentario_ids_unicos_aceptados",
              "filas_en_cassandra", "comentario_ids_unicos_en_cassandra", "perdidos",
              "alterados", "escritos_sin_confirmacion", "lecturas_totales",
              "lecturas_con_respuesta_incoherente"]:
        md.write(f"| {k} | {resultado[k]} |\n")
    md.write(f"| duplicados_por_reintento (ids / filas extra) | "
             f"{len(dup_reintento)} / {resultado['duplicados_por_reintento']['filas_extra']} |\n")
    md.write(f"| duplicados_inesperados (ids / filas extra) | "
             f"{len(dup_inesperado)} / {resultado['duplicados_inesperados']['filas_extra']} |\n")
    md.write(f"\nRechazos por causa: `{dict(rechazos)}`\n\n")
    md.write(f"Filas por particion (partido, ventana UTC): `{por_particion}`\n\n")
    md.write(f"Redis: `{json.dumps(redis_chk, ensure_ascii=False)}`\n\n")
    # Conciliacion con un contador INDEPENDIENTE: cuantas escrituras conto la
    # propia Cassandra (nodetool, antes/despues) contra las filas leidas con cqlsh
    # y los 201 que vio el cliente. Son tres fuentes distintas del mismo hecho.
    escr_nodetool = meta.get("cassandra_delta", {}).get("escrituras_que_llegaron_a_cassandra")
    resultado["conciliacion"] = {
        "201_vistos_por_el_cliente": resultado["escrituras_aceptadas_201"],
        "escrituras_contadas_por_cassandra_nodetool": escr_nodetool,
        "filas_leidas_con_cqlsh": len(filas),
    }
    md.write(f"Conciliacion de tres fuentes: 201 vistos por el cliente = "
             f"{resultado['escrituras_aceptadas_201']}; escrituras contadas por Cassandra "
             f"(nodetool) = {escr_nodetool}; filas leidas con cqlsh = {len(filas)}\n\n")
    if escr_nodetool is not None and int(escr_nodetool) != len(filas):
        resultado["observaciones"].append(
            "nodetool y cqlsh no coinciden: revisar si hubo otras escrituras en la tabla "
            "durante la prueba (otro proceso) o si el contador se reinicio.")
    for p in problemas:
        md.write(f"- PROBLEMA: {p}\n")
    for o in resultado["observaciones"]:
        md.write(f"- Observacion: {o}\n")
    texto = md.getvalue().replace("__VEREDICTO__", resultado["veredicto"])
    (dir_corrida / "integridad.md").write_text(texto, encoding="utf-8")
    escribir_json(dir_corrida / "integridad.json", resultado)

    print(texto)
    print(f"Guardado en {dir_corrida / 'integridad.json'}")


if __name__ == "__main__":
    main()
