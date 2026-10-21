#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generador reproducible del subgrafo del Fixture 2030 (Hito 5 - Neo4j).

Reutiliza los MISMOS identificadores del modulo documental (Hito 4): lee
equipos.json y jugadores.json y conserva el campo `codigo` de cada entidad
(RF5, RNF6). A partir de ahi genera, de forma determinista (semilla fija),
la informacion relacional que el grafo necesita y que no vive en Mongo:
grupos, sedes/estadios, partidos de la fase de grupos y eventos.

Salida: CSVs en ./import listos para LOAD CSV desde Neo4j.
Verifica integridad referencial real antes de escribir.
"""
import json, csv, random, os
from collections import Counter, defaultdict

random.seed(2030)  # determinismo -> misma carga siempre (RNF4)

AQUI = os.path.dirname(os.path.abspath(__file__))
IMPORT = os.path.join(AQUI, "import")
# Fuente: datos reales del Hito 4 (modulo documental del companero de equipo)
SRC = "/mnt/project"

equipos = json.load(open(os.path.join(SRC, "equipos.json"), encoding="utf-8"))
jugadores = json.load(open(os.path.join(SRC, "jugadores.json"), encoding="utf-8"))
assert len(equipos) == 64, len(equipos)
assert len(jugadores) >= 1000, len(jugadores)

codigos_equipo = [e["codigo"] for e in equipos]

# -----------------------------------------------------------------------------
# 1) Grupos: 16 grupos (A-P) de 4 equipos. Asignacion determinista.
# -----------------------------------------------------------------------------
GRUPOS = [chr(ord("A") + i) for i in range(16)]
orden = codigos_equipo[:]
random.shuffle(orden)  # seeded
grupo_de = {}
equipos_de_grupo = defaultdict(list)
for i, cod in enumerate(orden):
    g = GRUPOS[i % 16]
    grupo_de[cod] = g
    equipos_de_grupo[g].append(cod)

# -----------------------------------------------------------------------------
# 2) Sedes / estadios en los 6 paises anfitriones (consistente con anfitrion=true
#    del Hito 4: ARG, URU, PAR, ESP, POR, MAR).
# -----------------------------------------------------------------------------
sedes = [
    ("MONU", "Estadio Monumental",              "Buenos Aires", "Argentina"),
    ("KEMP", "Estadio Mario Alberto Kempes",    "Cordoba",      "Argentina"),
    ("CENT", "Estadio Centenario",              "Montevideo",   "Uruguay"),
    ("CHAC", "Estadio Defensores del Chaco",    "Asuncion",     "Paraguay"),
    ("BERN", "Estadio Santiago Bernabeu",       "Madrid",       "Espana"),
    ("CAMP", "Spotify Camp Nou",                "Barcelona",    "Espana"),
    ("CART", "Estadio de La Cartuja",           "Sevilla",      "Espana"),
    ("LUZ",  "Estadio da Luz",                  "Lisboa",       "Portugal"),
    ("DRAG", "Estadio do Dragao",               "Oporto",       "Portugal"),
    ("MOH5", "Complejo Deportivo Mohammed V",   "Casablanca",   "Marruecos"),
    ("TANG", "Gran Estadio de Tanger",          "Tanger",       "Marruecos"),
    ("MOUL", "Estadio Principe Moulay Abdellah","Rabat",        "Marruecos"),
]
codigos_sede = [s[0] for s in sedes]

# -----------------------------------------------------------------------------
# 3) Partidos: fase de grupos, round-robin dentro de cada grupo (6 por grupo).
# -----------------------------------------------------------------------------
partidos = []          # (codigo, fecha, fase, grupo, golesL, golesV, sedeCodigo)
participaciones = []   # (partidoCodigo, equipoCodigo, condicion)
n = 0
dia_base = 13  # 13 de junio de 2030 en adelante
for g in GRUPOS:
    eqs = equipos_de_grupo[g]
    pares = [(a, b) for i, a in enumerate(eqs) for b in eqs[i + 1:]]  # 6 pares
    for (local, visita) in pares:
        n += 1
        cod = f"F2030-{n:03d}"
        dia = dia_base + (n % 18)  # reparte las fechas en la ventana de grupos
        fecha = f"2030-06-{dia:02d}"
        gl = random.randint(0, 4)
        gv = random.randint(0, 4)
        sede = random.choice(codigos_sede)
        partidos.append((cod, fecha, "Grupos", g, gl, gv, sede))
        participaciones.append((cod, local, "local"))
        participaciones.append((cod, visita, "visitante"))

# indice rapido de jugadores por equipo (para asignar autores de eventos)
jug_por_equipo = defaultdict(list)
for j in jugadores:
    jug_por_equipo[j["equipoCodigo"]].append(j["codigo"])

# -----------------------------------------------------------------------------
# 4) Eventos: goles (protagonizados por un jugador del equipo que anoto) y
#    tarjetas. Cada evento se vincula a su partido.
# -----------------------------------------------------------------------------
eventos = []  # (codigo, tipo, minuto, partidoCodigo, jugadorCodigo)
ev = 0
# equipos local/visitante por partido para elegir autor coherente
local_de = {}
visita_de = {}
for (pc, eq, cond) in participaciones:
    (local_de if cond == "local" else visita_de)[pc] = eq

for (cod, fecha, fase, g, gl, gv, sede) in partidos:
    # goles del local
    for _ in range(gl):
        ev += 1
        autor = random.choice(jug_por_equipo[local_de[cod]])
        eventos.append((f"EV-{ev:04d}", "Gol", random.randint(1, 90), cod, autor))
    # goles del visitante
    for _ in range(gv):
        ev += 1
        autor = random.choice(jug_por_equipo[visita_de[cod]])
        eventos.append((f"EV-{ev:04d}", "Gol", random.randint(1, 90), cod, autor))
    # 0..2 tarjetas, autor de cualquiera de los dos equipos
    for _ in range(random.randint(0, 2)):
        ev += 1
        equipo_t = random.choice([local_de[cod], visita_de[cod]])
        autor = random.choice(jug_por_equipo[equipo_t])
        eventos.append((f"EV-{ev:04d}", "Tarjeta", random.randint(1, 90), cod, autor))

# -----------------------------------------------------------------------------
# 5) VERIFICACION DE INTEGRIDAD REFERENCIAL (real, antes de escribir)
# -----------------------------------------------------------------------------
set_eq = set(codigos_equipo)
set_sede = set(codigos_sede)
set_part = {p[0] for p in partidos}
set_jug = {j["codigo"] for j in jugadores}

chequeos = {
    "64 equipos": len(equipos) == 64,
    ">=1000 jugadores": len(jugadores) >= 1000,
    "16 grupos de 4": all(len(v) == 4 for v in equipos_de_grupo.values()) and len(equipos_de_grupo) == 16,
    "todo jugador referencia equipo valido": all(j["equipoCodigo"] in set_eq for j in jugadores),
    "cada partido tiene 2 participaciones": all(
        sum(1 for x in participaciones if x[0] == p[0]) == 2 for p in partidos),
    "participaciones referencian equipos validos": all(x[1] in set_eq for x in participaciones),
    "rivales del mismo grupo": all(grupo_de[l] == grupo_de[v] for (pc) in set_part
        for l in [local_de[pc]] for v in [visita_de[pc]]),
    "partidos referencian sede valida": all(p[6] in set_sede for p in partidos),
    "eventos referencian partido valido": all(e[3] in set_part for e in eventos),
    "eventos referencian jugador valido": all(e[4] in set_jug for e in eventos),
    "sin codigos de partido duplicados": len(set_part) == len(partidos),
    "sin codigos de evento duplicados": len({e[0] for e in eventos}) == len(eventos),
}
print("=== VERIFICACION DE INTEGRIDAD DEL SUBGRAFO ===")
for k, v in chequeos.items():
    print(f"  [{'OK' if v else 'FALLA'}] {k}")
assert all(chequeos.values()), "Integridad no superada"

# -----------------------------------------------------------------------------
# 6) Escribir CSVs en ./import
# -----------------------------------------------------------------------------
def escribir(nombre, cabecera, filas):
    ruta = os.path.join(IMPORT, nombre)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cabecera)
        w.writerows(filas)
    print(f"  -> {nombre}: {len(filas)} filas")

print("\n=== ESCRITURA DE CSVs ===")
escribir("equipos.csv", ["codigo", "nombre", "confederacion", "rankingFIFA", "esAnfitrion", "grupo"],
         [(e["codigo"], e["nombre"], e["confederacion"], e["rankingFIFA"],
           str(bool(e.get("anfitrion"))).lower(), grupo_de[e["codigo"]]) for e in equipos])

escribir("jugadores.csv", ["codigo", "nombre", "posicion", "dorsal", "equipoCodigo"],
         [(j["codigo"], j["nombre"], j["posicion"], j["dorsal"], j["equipoCodigo"]) for j in jugadores])

escribir("sedes.csv", ["codigo", "nombre", "ciudad", "pais"], sedes)

escribir("partidos.csv", ["codigo", "fecha", "fase", "grupo", "golesLocal", "golesVisitante", "sedeCodigo"],
         partidos)

escribir("participaciones.csv", ["partidoCodigo", "equipoCodigo", "condicion"], participaciones)

escribir("eventos.csv", ["codigo", "tipo", "minuto", "partidoCodigo", "jugadorCodigo"], eventos)

# -----------------------------------------------------------------------------
# 7) Resumen para la evidencia
# -----------------------------------------------------------------------------
resumen = {
    "equipos": len(equipos),
    "jugadores": len(jugadores),
    "sedes": len(sedes),
    "partidos": len(partidos),
    "participaciones": len(participaciones),
    "eventos": len(eventos),
    "eventos_por_tipo": dict(Counter(e[1] for e in eventos)),
    "relaciones_estimadas": {
        "PERTENECE_A": len(jugadores),
        "DISPUTA": len(participaciones),
        "SE_JUEGA_EN": len(partidos),
        "OCURRE_EN": len(eventos),
        "PROTAGONIZADO_POR": len(eventos),
    },
}
json.dump(resumen, open(os.path.join(AQUI, "_resumen.json"), "w"), ensure_ascii=False, indent=2)
print("\n=== RESUMEN ===")
print(json.dumps(resumen, ensure_ascii=False, indent=2))
print("\n[OK] Fixture generado y verificado.")
