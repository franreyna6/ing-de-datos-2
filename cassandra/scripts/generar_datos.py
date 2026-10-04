#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generador reproducible de comentarios del Fixture 2030 (Hito 6, Cassandra).

Produce dos CSV con las MISMAS filas, una por cada tabla de acceso del modelo
(duplicacion controlada, ver docs/modelo_tabular.md):

    comentarios_por_partido.csv   -> tabla comentarios_por_partido
    comentarios_por_usuario.csv   -> tabla comentarios_por_usuario

Los CSV se cargan con COPY desde cqlsh (ver scripts/carga_o_prueba.sh).

Reproducibilidad (RNF3, RNF7):
  * Semilla fija: la misma semilla y los mismos argumentos producen exactamente
    los mismos archivos, incluidos los comentario_id (uuid).
  * Como la clave primaria es identica en cada corrida, volver a cargar el CSV
    sobrescribe las mismas filas (upsert) y NO duplica datos.

Origen de los datos de contexto (coherencia con el Hito 5):
  * data/origen/partidos.csv, equipos.csv, participaciones.csv, eventos.csv
    (los mismos CSV del modulo de grafos).
  * Los comentarios son SINTETICOS (los usuarios y los mensajes no existen en
    hitos previos). La popularidad de cada partido sale del ranking FIFA de sus
    equipos y los picos de actividad se ubican despues de goles y tarjetas.

Uso:
    python scripts/generar_datos.py                       # 1.100.000 de filas
    python scripts/generar_datos.py --total 20000         # prueba rapida
    python scripts/generar_datos.py --total 1100000 --partido-caliente F2030-001

Solo usa la biblioteca estandar de Python.
"""
import argparse
import csv
import math
import os
import random
import statistics
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

# --- Supuestos de modelado (documentados en docs/decisiones_de_particionamiento.md)
VENTANA_MIN = 5            # tamano de la ventana temporal (bucket) en minutos
HORA_INICIO_UTC = 20       # hora de inicio supuesta de todos los partidos (UTC)
N_USUARIOS = 200_000       # usuarios sinteticos distintos
BYTES_FILA_ESTIMADOS = 170  # estimacion de bytes por fila (se compara en rendimiento.md)

ESTADOS = [("visible", 0.93), ("pendiente", 0.04), ("oculto", 0.03)]

FRASES = [
    "Que partidazo", "Vamos {eq}", "Gol, gol, gol", "No lo puedo creer",
    "Arbitro vendido", "Increible lo que esta pasando", "Que atajada",
    "Esto no se puede creer", "Todo el pais esta mirando", "Dale {eq} dale",
    "Que error de la defensa", "Hay que cambiar el esquema", "Tremenda jugada",
    "Estoy temblando", "Aguante {eq}", "El estadio explota", "Que nervios",
    "Eso era penal", "Mejor partido del grupo", "Esto es el Mundial",
    "Que golazo", "Se viene el empate", "Fin del primer tiempo, que sufrimiento",
    "Imposible no emocionarse", "Orgullo total", "Vamos que se puede",
]

NS = uuid.UUID("00000000-0000-0000-0000-000000002030")


def leer_csv(ruta):
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def elegir_estado(rnd):
    x, acum = rnd.random(), 0.0
    for nombre, p in ESTADOS:
        acum += p
        if x < acum:
            return nombre
    return ESTADOS[-1][0]


def piso_ventana(dt):
    """Inicio de la ventana de VENTANA_MIN minutos que contiene a dt (UTC)."""
    minuto = (dt.minute // VENTANA_MIN) * VENTANA_MIN
    return dt.replace(minute=minuto, second=0, microsecond=0)


def fmt(dt):
    # Formato por defecto que acepta COPY para timestamp: %Y-%m-%d %H:%M:%S%z
    return dt.strftime("%Y-%m-%d %H:%M:%S+0000")


def main():
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--total", type=int, default=1_100_000, help="cantidad total de comentarios")
    ap.add_argument("--semilla", type=int, default=2030)
    ap.add_argument("--origen", default=os.path.join(base, "data", "origen"))
    ap.add_argument("--salida", default=os.path.join(base, "data", "generado"))
    ap.add_argument("--partido-caliente", default=None,
                    help="codigo del partido de trafico extraordinario (por defecto, el de mayor popularidad)")
    ap.add_argument("--cuota-caliente", type=float, default=0.12,
                    help="fraccion del total que recibe el partido caliente (default 0.12)")
    args = ap.parse_args()

    os.makedirs(args.salida, exist_ok=True)

    partidos = leer_csv(os.path.join(args.origen, "partidos.csv"))
    equipos = {e["codigo"]: e for e in leer_csv(os.path.join(args.origen, "equipos.csv"))}
    participaciones = leer_csv(os.path.join(args.origen, "participaciones.csv"))
    eventos = leer_csv(os.path.join(args.origen, "eventos.csv"))

    # equipos de cada partido
    eq_partido = defaultdict(dict)
    for p in participaciones:
        eq_partido[p["partidoCodigo"]][p["condicion"]] = p["equipoCodigo"]
    # minutos de eventos (goles y tarjetas) de cada partido
    min_eventos = defaultdict(list)
    for e in eventos:
        min_eventos[e["partidoCodigo"]].append(int(e["minuto"]))

    # --- popularidad: 1/sqrt(rankL * rankV); el mejor ranking atrae mas comentarios
    peso = {}
    for p in partidos:
        c = p["codigo"]
        rl = int(equipos[eq_partido[c]["local"]]["rankingFIFA"])
        rv = int(equipos[eq_partido[c]["visitante"]]["rankingFIFA"])
        peso[c] = 1.0 / math.sqrt(rl * rv)

    caliente = args.partido_caliente or max(peso, key=peso.get)
    if caliente not in peso:
        raise SystemExit(f"Partido caliente inexistente: {caliente}")

    n_caliente = round(args.total * args.cuota_caliente)
    resto = args.total - n_caliente
    otros = [c for c in peso if c != caliente]
    suma = sum(peso[c] for c in otros)
    cuota = {c: int(resto * peso[c] / suma) for c in otros}
    # el redondeo hacia abajo deja un resto que se reparte de a uno
    faltan = resto - sum(cuota.values())
    for c in sorted(otros, key=lambda x: -peso[x])[:faltan]:
        cuota[c] += 1
    cuota[caliente] = n_caliente

    fecha_partido = {p["codigo"]: p["fecha"] for p in partidos}
    nombre_eq = {c: e["nombre"] for c, e in equipos.items()}

    filas = []  # (partido, ventana, creado_en, id, usuario, contenido, estado, likes)
    for p in partidos:
        c = p["codigo"]
        n = cuota[c]
        rnd = random.Random(f"{args.semilla}-{c}")
        inicio = datetime.strptime(p["fecha"], "%Y-%m-%d").replace(
            hour=HORA_INICIO_UTC, tzinfo=timezone.utc)
        mins_ev = min_eventos.get(c, [])
        nombres = [nombre_eq[eq_partido[c]["local"]], nombre_eq[eq_partido[c]["visitante"]]]
        for _ in range(n):
            r = rnd.random()
            if r < 0.10:                       # previa: 15 min antes del inicio
                off = rnd.uniform(-15 * 60, 0)
            elif r < 0.20:                     # posterior al pitazo final
                off = rnd.uniform(110 * 60, 125 * 60)
            elif r < 0.65 or not mins_ev:      # flujo base durante el partido
                off = rnd.uniform(0, 110 * 60)
            else:                              # pico despues de un gol o tarjeta
                m = rnd.choice(mins_ev)
                off = m * 60 + min(rnd.expovariate(1 / 90.0), 600)
            ts = inicio + timedelta(seconds=int(off))
            uid = f"U{int(N_USUARIOS * rnd.random() ** 2) + 1:06d}"
            cid = uuid.UUID(int=rnd.getrandbits(128), version=4)
            texto = rnd.choice(FRASES).format(eq=rnd.choice(nombres))
            likes = min(int(rnd.expovariate(0.4)), 500) if rnd.random() < 0.35 else 0
            filas.append((c, piso_ventana(ts), ts, cid, uid, texto, elegir_estado(rnd), likes))

    # --- CSV 1: comentarios_por_partido (ordenado por particion y clustering)
    filas.sort(key=lambda f: (f[0], f[1], f[2], str(f[3])))
    ruta1 = os.path.join(args.salida, "comentarios_por_partido.csv")
    with open(ruta1, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["partido_id", "ventana", "creado_en", "comentario_id",
                    "usuario_id", "contenido", "estado", "likes"])
        for fi in filas:
            w.writerow([fi[0], fmt(fi[1]), fmt(fi[2]), fi[3], fi[4], fi[5], fi[6], fi[7]])

    # --- CSV 2: comentarios_por_usuario (misma informacion, otra clave de acceso)
    # No incluye 'likes': es la metrica que mas cambia y vive solo en la tabla
    # principal (ver docs/modelo_tabular.md, duplicacion controlada).
    filas.sort(key=lambda f: (f[4], f[2], str(f[3])))
    ruta2 = os.path.join(args.salida, "comentarios_por_usuario.csv")
    with open(ruta2, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["usuario_id", "creado_en", "comentario_id", "partido_id",
                    "ventana", "contenido", "estado"])
        for fi in filas:
            w.writerow([fi[4], fmt(fi[2]), fi[3], fi[0], fmt(fi[1]), fi[5], fi[6]])

    # --- Resumen de distribucion (evidencia de RF11 y RNF5)
    por_particion = Counter((f[0], f[1]) for f in filas)
    por_partido = Counter(f[0] for f in filas)
    por_usuario = Counter(f[4] for f in filas)
    por_estado = Counter(f[6] for f in filas)
    tam = sorted(por_particion.values())
    ventanas_partido = Counter(k[0] for k in por_particion)

    def q(vals, p):
        return vals[min(len(vals) - 1, int(len(vals) * p))]

    lineas = []
    A = lineas.append
    A("RESUMEN DE DISTRIBUCION DE LA CARGA GENERADA")
    A(f"semilla={args.semilla} total_solicitado={args.total} ventana={VENTANA_MIN} min "
      f"inicio_supuesto={HORA_INICIO_UTC}:00 UTC")
    A(f"filas_generadas={len(filas)} (se escriben en 2 tablas -> {2 * len(filas)} filas fisicas)")
    A(f"partidos={len(por_partido)} usuarios_distintos={len(por_usuario)}")
    A("")
    A("Estados de moderacion:")
    for est, n in por_estado.most_common():
        A(f"  {est:<10} {n:>9}  ({100 * n / len(filas):.2f}%)")
    A("")
    A(f"Partido caliente: {caliente} -> {por_partido[caliente]} comentarios "
      f"({100 * por_partido[caliente] / len(filas):.1f}% del total) en "
      f"{ventanas_partido[caliente]} ventanas")
    A("Top 5 partidos por comentarios:")
    for c, n in por_partido.most_common(5):
        A(f"  {c}  {n:>8}")
    A(f"Partido con menos comentarios: {min(por_partido.items(), key=lambda x: x[1])}")
    A("")
    A("Particiones de comentarios_por_partido = (partido_id, ventana):")
    A(f"  cantidad={len(por_particion)}")
    A(f"  filas por particion: min={tam[0]} mediana={int(statistics.median(tam))} "
      f"p95={q(tam, 0.95)} p99={q(tam, 0.99)} max={tam[-1]}")
    A(f"  bytes estimados de la particion maxima (~{BYTES_FILA_ESTIMADOS} B/fila): "
      f"{tam[-1] * BYTES_FILA_ESTIMADOS / 1024 / 1024:.2f} MiB (ESTIMACION, no medicion)")
    A("  Top 10 particiones mas grandes:")
    for (c, v), n in por_particion.most_common(10):
        A(f"    {c}  {fmt(v)}  {n:>7} filas")
    A("")
    ult = sorted(por_usuario.values())
    A("Particiones de comentarios_por_usuario = (usuario_id):")
    A(f"  cantidad={len(por_usuario)}")
    A(f"  filas por usuario: min={ult[0]} mediana={int(statistics.median(ult))} "
      f"p99={q(ult, 0.99)} max={ult[-1]}")
    A("  Top 5 usuarios con mas comentarios:")
    for u, n in por_usuario.most_common(5):
        A(f"    {u}  {n:>6}")
    A("")
    A(f"Archivos: {os.path.relpath(ruta1)} | {os.path.relpath(ruta2)}")
    texto = "\n".join(lineas) + "\n"
    with open(os.path.join(args.salida, "resumen_distribucion.txt"), "w", encoding="utf-8") as f:
        f.write(texto)
    print(texto)


if __name__ == "__main__":
    main()
