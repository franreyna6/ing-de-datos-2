#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generador reproducible de la muestra de Redis del Fixture 2030 (Hito 7).

Produce:
    scripts/carga_muestra.redis             comandos de carga (se ejecuta con ejecutar_bloques.sh)
    docs/evidencia/distribucion_generada.txt  resumen de lo generado

Reproducibilidad (RNF3):
  * Semilla fija: la misma semilla y los mismos argumentos producen exactamente
    el mismo archivo.
  * La carga es idempotente: usa HSET/SET/ZADD con claves fijas, de modo que
    volver a cargarla sobrescribe las mismas claves y no duplica datos.

Origen de los datos (coherencia con los hitos 4 y 5):
  * data/origen/partidos.csv, equipos.csv, participaciones.csv y jugadores.csv
    son los CSV del modulo de grafos (Hito 5). Con ellos se arman las copias de
    cache de la ficha de partido y de equipo, y los candidatos de las encuestas.
  * Las SESIONES y los contadores de visitas/votos son SINTETICOS: los usuarios
    y la actividad no existen en hitos previos. No hay datos personales ni
    tokens reales (RNF7).

Uso:
    python scripts/generar_datos.py
    python scripts/generar_datos.py --sesiones 500 --semilla 2030

Solo usa la biblioteca estandar de Python.
"""
import argparse
import csv
import json
import os
import random
from collections import Counter
from datetime import datetime, timedelta

# --- Decisiones de ciclo de vida (se justifican en docs/ciclo_de_vida_e_invalidacion.md) ---
TTL_SESION = 1800        # 30 minutos de inactividad
TTL_CACHE_PARTIDO = 300  # 5 minutos: maximo de obsolescencia admisible de una ficha de partido
TTL_CACHE_EQUIPO = 3600  # 1 hora: los datos de un equipo casi no cambian

PARTIDOS_CACHE_CALIENTES = 20   # fichas de partido precargadas (los demas quedan "frios")
EQUIPOS_CACHE_CALIENTES = 16    # fichas de equipo precargadas
PARTIDOS_CON_ENCUESTA = 12      # encuestas "figura del partido"
JUGADORES_POR_EQUIPO = 3        # candidatos por equipo en cada encuesta

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)


def leer_csv(nombre):
    with open(os.path.join(RAIZ, "data", "origen", nombre), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def comillas(texto):
    """Entrecomilla con comillas simples para redis-cli (el JSON lleva comillas dobles)."""
    return "'" + texto.replace("\\", "\\\\").replace("'", "\\'") + "'"


def json_compacto(objeto):
    # ensure_ascii=True: el archivo queda en ASCII puro (acentos como \uXXXX validos en JSON)
    return json.dumps(objeto, separators=(",", ":"), ensure_ascii=True)


def main():
    ap = argparse.ArgumentParser(description="Genera la muestra de Redis del Fixture 2030")
    ap.add_argument("--sesiones", type=int, default=200, help="cantidad de sesiones (default 200)")
    ap.add_argument("--semilla", type=int, default=2030, help="semilla del generador (default 2030)")
    args = ap.parse_args()
    rng = random.Random(args.semilla)

    partidos = leer_csv("partidos.csv")
    equipos = leer_csv("equipos.csv")
    participaciones = leer_csv("participaciones.csv")
    jugadores = leer_csv("jugadores.csv")

    lineas = []
    add = lineas.append
    add("# =============================================================================")
    add("# carga_muestra.redis - Hito 7 (Grupo 8)")
    add("# ARCHIVO GENERADO por scripts/generar_datos.py (semilla %d). No editar a mano." % args.semilla)
    add("# Carga idempotente: HSET/SET/ZADD con claves fijas (repetir no duplica datos).")
    add("# Se ejecuta con: sh /scripts/ejecutar_bloques.sh /scripts/carga_muestra.redis carga")
    add("# (redis-cli no admite comentarios con # al leer un archivo: el ejecutor los filtra).")
    add("# =============================================================================")
    add("")

    # ------------------------------------------------------------------ SESIONES
    add("# --- 1. Sesiones de usuarios (Hash + TTL de %d s = inactividad) ---" % TTL_SESION)
    add("# Clave: sesion:<sesionId>. Campos: usuario_id, rol, estado, creada_en, ultimo_acceso, acciones.")
    base = datetime(2030, 6, 14, 12, 0, 0)
    roles = rng.choices(["fan", "periodista", "admin"], weights=[92, 6, 2], k=args.sesiones)
    for i in range(1, args.sesiones + 1):
        sid, uid = "S%04d" % i, "U%04d" % i
        creada = base + timedelta(seconds=rng.randint(0, 6 * 3600))
        ultimo = creada + timedelta(seconds=rng.randint(60, 2 * 3600))
        acciones = rng.randint(1, 60)
        add("MULTI")
        add("HSET sesion:%s usuario_id %s rol %s estado activa creada_en %s ultimo_acceso %s acciones %d" % (
            sid, uid, roles[i - 1], creada.strftime("%Y-%m-%dT%H:%M:%SZ"),
            ultimo.strftime("%Y-%m-%dT%H:%M:%SZ"), acciones))
        add("EXPIRE sesion:%s %d" % (sid, TTL_SESION))
        add("EXEC")
    add("")

    # --------------------------------------------------------------------- CACHE
    add("# --- 2. Cache de la ficha de partido (String JSON + TTL de %d s) ---" % TTL_CACHE_PARTIDO)
    add("# Fuente de verdad: grafo de Neo4j (Hito 5, nodo Partido). Se precargan los primeros %d;" % PARTIDOS_CACHE_CALIENTES)
    add("# el resto queda sin copia en cache para poder demostrar cache miss.")
    for p in partidos[:PARTIDOS_CACHE_CALIENTES]:
        ficha = {
            "codigo": p["codigo"], "fecha": p["fecha"], "fase": p["fase"], "grupo": p["grupo"],
            "golesLocal": int(p["golesLocal"]), "golesVisitante": int(p["golesVisitante"]),
            "sedeCodigo": p["sedeCodigo"],
        }
        add("SET cache:partido:%s %s EX %d" % (p["codigo"], comillas(json_compacto(ficha)), TTL_CACHE_PARTIDO))
    add("")
    add("# --- 3. Cache de la ficha de equipo (String JSON + TTL de %d s) ---" % TTL_CACHE_EQUIPO)
    add("# Fuente de verdad: coleccion equipos de MongoDB (Hito 4).")
    for e in equipos[:EQUIPOS_CACHE_CALIENTES]:
        ficha = {
            "codigo": e["codigo"], "nombre": e["nombre"], "confederacion": e["confederacion"],
            "rankingFIFA": int(e["rankingFIFA"]), "esAnfitrion": e["esAnfitrion"].strip().lower() == "true",
            "grupo": e["grupo"],
        }
        add("SET cache:equipo:%s %s EX %d" % (e["codigo"], comillas(json_compacto(ficha)), TTL_CACHE_EQUIPO))
    add("")

    # ------------------------------------------------------ CONTADORES Y RANKINGS
    add("# --- 4. Contador de visitas por partido (String entero, SIN TTL: conservar) ---")
    add("# Acotado por el dominio: un contador por cada uno de los %d partidos." % len(partidos))
    visitas = {}
    for p in partidos:
        visitas[p["codigo"]] = rng.randint(2000, 60000)
        add("SET partido:%s:visitas %d" % (p["codigo"], visitas[p["codigo"]]))
    add("")

    add("# --- 5. Encuesta 'figura del partido' (Sorted Set, SIN TTL: conservar) ---")
    add("# Candidatos: %d jugadores de cada equipo (jugadores.csv); miembro = codigo de jugador." % JUGADORES_POR_EQUIPO)
    por_equipo = {}
    for j in jugadores:
        por_equipo.setdefault(j["equipoCodigo"], []).append(j["codigo"])
    equipos_de = {}
    for pa in participaciones:
        equipos_de.setdefault(pa["partidoCodigo"], []).append(pa["equipoCodigo"])
    votos_total = 0
    for p in partidos[:PARTIDOS_CON_ENCUESTA]:
        partes = []
        for eq in equipos_de[p["codigo"]]:
            for cod in por_equipo[eq][:JUGADORES_POR_EQUIPO]:
                puntaje = rng.randint(5, 400)
                votos_total += puntaje
                partes.append("%d %s" % (puntaje, cod))
        add("ZADD encuesta:%s:figura %s" % (p["codigo"], " ".join(partes)))
    add("")

    destino = os.path.join(AQUI, "carga_muestra.redis")
    with open(destino, "w", newline="\n", encoding="ascii") as f:
        f.write("\n".join(lineas) + "\n")

    # ------------------------------------------------------------ DISTRIBUCION
    comandos = [l for l in lineas if l and not l.startswith("#")]
    cont_roles = Counter(roles)
    v = list(visitas.values())
    resumen = [
        "Distribucion de la muestra generada (semilla %d)" % args.semilla,
        "Generador: scripts/generar_datos.py - archivo: scripts/carga_muestra.redis",
        "",
        "Comandos del archivo (sin comentarios): %d" % len(comandos),
        "",
        "Sesiones (clave sesion:<id>, Hash, TTL %d s): %d" % (TTL_SESION, args.sesiones),
        "  rol fan:        %d" % cont_roles["fan"],
        "  rol periodista: %d" % cont_roles["periodista"],
        "  rol admin:      %d" % cont_roles["admin"],
        "  estado activa:  %d" % args.sesiones,
        "",
        "Cache de ficha de partido (cache:partido:<codigo>, String JSON, TTL %d s): %d de %d partidos" % (
            TTL_CACHE_PARTIDO, PARTIDOS_CACHE_CALIENTES, len(partidos)),
        "Cache de ficha de equipo (cache:equipo:<codigo>, String JSON, TTL %d s): %d de %d equipos" % (
            TTL_CACHE_EQUIPO, EQUIPOS_CACHE_CALIENTES, len(equipos)),
        "",
        "Contadores de visitas (partido:<codigo>:visitas, String, sin TTL): %d" % len(partidos),
        "  minimo %d - maximo %d - suma %d" % (min(v), max(v), sum(v)),
        "",
        "Encuestas figura del partido (encuesta:<codigo>:figura, Sorted Set, sin TTL): %d" % PARTIDOS_CON_ENCUESTA,
        "  candidatos por encuesta: %d (jugadores de ambos equipos) - votos cargados en total: %d" % (
            2 * JUGADORES_POR_EQUIPO, votos_total),
        "",
        "Claves totales cargadas: %d" % (args.sesiones + PARTIDOS_CACHE_CALIENTES + EQUIPOS_CACHE_CALIENTES
                                         + len(partidos) + PARTIDOS_CON_ENCUESTA),
        "  con TTL: %d - sin TTL (conservadas por decision): %d" % (
            args.sesiones + PARTIDOS_CACHE_CALIENTES + EQUIPOS_CACHE_CALIENTES,
            len(partidos) + PARTIDOS_CON_ENCUESTA),
    ]
    ruta_resumen = os.path.join(RAIZ, "docs", "evidencia", "distribucion_generada.txt")
    os.makedirs(os.path.dirname(ruta_resumen), exist_ok=True)
    with open(ruta_resumen, "w", newline="\n", encoding="ascii") as f:
        f.write("\n".join(resumen) + "\n")
    print("\n".join(resumen))


if __name__ == "__main__":
    main()
