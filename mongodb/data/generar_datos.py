#!/usr/bin/env python3
"""
generar_datos.py
--------------------------------------------------------------------------------
Genera datos sinteticos y reproducibles para el modulo documental del Fixture
2030:
  - 64 equipos (selecciones nacionales)
  - 1024 jugadores (16 por equipo)

Escribe:
  - equipos.json
  - jugadores.json

Los datos son sinteticos: los nombres de jugadores son generados por script
para evitar reproducir personas reales. Los datos de equipos (codigo FIFA,
nombre, confederacion) son reales, publicos y estables.

La generacion es determinista: usa semilla fija (random.seed(2030)) para que
dos ejecuciones distintas produzcan exactamente los mismos JSON. Esto asegura
la reproducibilidad exigida por RF8 y RNF1.

Uso:
  python3 generar_datos.py
"""

import json
import random
import string
from datetime import date, datetime, timezone

random.seed(2030)  # semilla fija -> generacion reproducible

# =============================================================================
# 64 selecciones nacionales para el Fixture 2030
# -----------------------------------------------------------------------------
# Distribucion por confederacion: UEFA 16, CONMEBOL 10, CONCACAF 8, CAF 12,
# AFC 12, OFC 6. Total: 64. Anfitriones marcados (ARG, URU, PAR, ESP, POR,
# MAR) segun el formato centenario del Mundial 2030.
# =============================================================================
EQUIPOS_BASE = [
    # (codigo, nombre, confederacion, ranking, sedeBase, DT, nacionalidadDT, colores)
    # --- CONMEBOL (10) ---
    ("ARG", "Argentina", "CONMEBOL", 1, "Buenos Aires", "Lionel Scaloni", "Argentina", ["celeste", "blanco"]),
    ("BRA", "Brasil", "CONMEBOL", 5, "Rio de Janeiro", "Dorival Junior", "Brasil", ["amarillo", "verde"]),
    ("URU", "Uruguay", "CONMEBOL", 16, "Montevideo", "Marcelo Bielsa", "Argentina", ["celeste"]),
    ("COL", "Colombia", "CONMEBOL", 12, "Bogota", "Nestor Lorenzo", "Argentina", ["amarillo", "azul", "rojo"]),
    ("ECU", "Ecuador", "CONMEBOL", 31, "Quito", "Sebastian Beccacece", "Argentina", ["amarillo", "azul"]),
    ("PAR", "Paraguay", "CONMEBOL", 48, "Asuncion", "Gustavo Alfaro", "Argentina", ["rojo", "blanco", "azul"]),
    ("CHI", "Chile", "CONMEBOL", 45, "Santiago", "Ricardo Gareca", "Argentina", ["rojo", "blanco"]),
    ("PER", "Peru", "CONMEBOL", 40, "Lima", "Oscar Ibanez", "Argentina", ["blanco", "rojo"]),
    ("VEN", "Venezuela", "CONMEBOL", 50, "Caracas", "Fernando Batista", "Argentina", ["vinotinto"]),
    ("BOL", "Bolivia", "CONMEBOL", 85, "La Paz", "Oscar Villegas", "Bolivia", ["verde", "blanco"]),
    # --- UEFA (16) ---
    ("ESP", "Espana", "UEFA", 2, "Madrid", "Luis de la Fuente", "Espana", ["rojo", "amarillo"]),
    ("FRA", "Francia", "UEFA", 3, "Paris", "Didier Deschamps", "Francia", ["azul", "blanco", "rojo"]),
    ("ENG", "Inglaterra", "UEFA", 4, "Londres", "Thomas Tuchel", "Alemania", ["blanco"]),
    ("POR", "Portugal", "UEFA", 6, "Lisboa", "Roberto Martinez", "Espana", ["rojo", "verde"]),
    ("NED", "Paises Bajos", "UEFA", 7, "Amsterdam", "Ronald Koeman", "Paises Bajos", ["naranja"]),
    ("BEL", "Belgica", "UEFA", 8, "Bruselas", "Domenico Tedesco", "Alemania", ["rojo", "amarillo", "negro"]),
    ("GER", "Alemania", "UEFA", 9, "Berlin", "Julian Nagelsmann", "Alemania", ["blanco", "negro"]),
    ("ITA", "Italia", "UEFA", 10, "Roma", "Luciano Spalletti", "Italia", ["azul"]),
    ("CRO", "Croacia", "UEFA", 11, "Zagreb", "Zlatko Dalic", "Croacia", ["rojo", "blanco"]),
    ("SUI", "Suiza", "UEFA", 18, "Berna", "Murat Yakin", "Suiza", ["rojo", "blanco"]),
    ("DEN", "Dinamarca", "UEFA", 19, "Copenhague", "Brian Riemer", "Dinamarca", ["rojo", "blanco"]),
    ("AUT", "Austria", "UEFA", 22, "Viena", "Ralf Rangnick", "Alemania", ["rojo", "blanco"]),
    ("UKR", "Ucrania", "UEFA", 25, "Kiev", "Serhiy Rebrov", "Ucrania", ["amarillo", "azul"]),
    ("SWE", "Suecia", "UEFA", 33, "Estocolmo", "Jon Dahl Tomasson", "Dinamarca", ["amarillo", "azul"]),
    ("POL", "Polonia", "UEFA", 34, "Varsovia", "Michal Probierz", "Polonia", ["blanco", "rojo"]),
    ("TUR", "Turquia", "UEFA", 27, "Estambul", "Vincenzo Montella", "Italia", ["rojo", "blanco"]),
    # --- CONCACAF (8) ---
    ("MEX", "Mexico", "CONCACAF", 17, "Ciudad de Mexico", "Javier Aguirre", "Mexico", ["verde", "blanco", "rojo"]),
    ("USA", "Estados Unidos", "CONCACAF", 15, "Washington D.C.", "Mauricio Pochettino", "Argentina", ["azul", "blanco", "rojo"]),
    ("CAN", "Canada", "CONCACAF", 30, "Toronto", "Jesse Marsch", "Estados Unidos", ["rojo", "blanco"]),
    ("PAN", "Panama", "CONCACAF", 41, "Ciudad de Panama", "Thomas Christiansen", "Espana", ["rojo", "azul", "blanco"]),
    ("CRC", "Costa Rica", "CONCACAF", 46, "San Jose", "Miguel Herrera", "Mexico", ["rojo", "blanco", "azul"]),
    ("JAM", "Jamaica", "CONCACAF", 55, "Kingston", "Steve McClaren", "Inglaterra", ["amarillo", "verde", "negro"]),
    ("HON", "Honduras", "CONCACAF", 72, "Tegucigalpa", "Reinaldo Rueda", "Colombia", ["azul", "blanco"]),
    ("HAI", "Haiti", "CONCACAF", 83, "Puerto Principe", "Sebastien Migne", "Francia", ["azul", "rojo"]),
    # --- CAF (12) ---
    ("MAR", "Marruecos", "CAF", 14, "Rabat", "Walid Regragui", "Marruecos", ["rojo", "verde"]),
    ("SEN", "Senegal", "CAF", 20, "Dakar", "Pape Thiaw", "Senegal", ["verde", "amarillo", "rojo"]),
    ("EGY", "Egipto", "CAF", 32, "El Cairo", "Hossam Hassan", "Egipto", ["rojo", "blanco", "negro"]),
    ("NGA", "Nigeria", "CAF", 43, "Abuya", "Eric Chelle", "Mali", ["verde", "blanco"]),
    ("ALG", "Argelia", "CAF", 36, "Argel", "Vladimir Petkovic", "Bosnia", ["verde", "blanco", "rojo"]),
    ("CIV", "Costa de Marfil", "CAF", 37, "Yamusukro", "Emerse Fae", "Costa de Marfil", ["naranja", "blanco", "verde"]),
    ("TUN", "Tunez", "CAF", 47, "Tunez", "Sami Trabelsi", "Tunez", ["rojo", "blanco"]),
    ("CMR", "Camerun", "CAF", 51, "Yaunde", "Marc Brys", "Belgica", ["verde", "rojo", "amarillo"]),
    ("MLI", "Mali", "CAF", 52, "Bamako", "Tom Saintfiet", "Belgica", ["verde", "amarillo", "rojo"]),
    ("GHA", "Ghana", "CAF", 71, "Acra", "Otto Addo", "Ghana", ["rojo", "amarillo", "verde"]),
    ("RSA", "Sudafrica", "CAF", 60, "Pretoria", "Hugo Broos", "Belgica", ["verde", "amarillo"]),
    ("BFA", "Burkina Faso", "CAF", 63, "Uagadugu", "Brama Traore", "Burkina Faso", ["rojo", "verde", "amarillo"]),
    # --- AFC (12) ---
    ("JPN", "Japon", "AFC", 15, "Tokio", "Hajime Moriyasu", "Japon", ["azul", "blanco"]),
    ("IRN", "Iran", "AFC", 21, "Teheran", "Amir Ghalenoei", "Iran", ["blanco", "rojo", "verde"]),
    ("KOR", "Corea del Sur", "AFC", 23, "Seul", "Hong Myung-bo", "Corea del Sur", ["rojo", "azul"]),
    ("AUS", "Australia", "AFC", 26, "Canberra", "Tony Popovic", "Australia", ["amarillo", "verde"]),
    ("KSA", "Arabia Saudita", "AFC", 58, "Riad", "Herve Renard", "Francia", ["verde", "blanco"]),
    ("QAT", "Qatar", "AFC", 44, "Doha", "Luis Garcia", "Espana", ["granate", "blanco"]),
    ("UAE", "Emiratos Arabes Unidos", "AFC", 65, "Abu Dabi", "Paulo Bento", "Portugal", ["blanco", "rojo", "verde", "negro"]),
    ("IRQ", "Irak", "AFC", 57, "Bagdad", "Jesus Casas", "Espana", ["blanco", "rojo", "negro"]),
    ("UZB", "Uzbekistan", "AFC", 68, "Taskent", "Timur Kapadze", "Uzbekistan", ["azul", "blanco", "verde"]),
    ("JOR", "Jordania", "AFC", 70, "Aman", "Jamal Sellami", "Marruecos", ["negro", "blanco", "verde", "rojo"]),
    ("CHN", "China", "AFC", 90, "Pekin", "Branko Ivankovic", "Croacia", ["rojo", "amarillo"]),
    ("VIE", "Vietnam", "AFC", 116, "Hanoi", "Kim Sang-sik", "Corea del Sur", ["rojo", "amarillo"]),
    # --- OFC (6) ---
    ("NZL", "Nueva Zelanda", "OFC", 89, "Wellington", "Darren Bazeley", "Inglaterra", ["blanco", "negro"]),
    ("NCL", "Nueva Caledonia", "OFC", 152, "Numea", "Johann Sidaner", "Francia", ["azul", "rojo", "verde"]),
    ("FIJ", "Fiyi", "OFC", 165, "Suva", "Rob Sherman", "Nueva Zelanda", ["azul", "blanco"]),
    ("SOL", "Islas Salomon", "OFC", 138, "Honiara", "Felipe Vega-Arango", "Espana", ["azul", "amarillo", "verde"]),
    ("VAN", "Vanuatu", "OFC", 168, "Port Vila", "Etienne Mermer", "Francia", ["rojo", "verde", "amarillo", "negro"]),
    ("TAH", "Tahiti", "OFC", 158, "Papeete", "Samuel Garcia", "Francia", ["rojo", "blanco"]),
]

assert len(EQUIPOS_BASE) == 64, f"Se esperaban 64 equipos, hay {len(EQUIPOS_BASE)}"

ANFITRIONES = {"ARG", "URU", "PAR", "ESP", "POR", "MAR"}

# =============================================================================
# Generacion de nombres sinteticos por region
# -----------------------------------------------------------------------------
# Nombres genericos y plausibles para cada zona geografica. NO representan
# jugadores reales; se generan de forma sintetica para el ejercicio.
# =============================================================================
NOMBRES_POR_CONFEDERACION = {
    "CONMEBOL": {
        "nombres": ["Juan", "Carlos", "Diego", "Sergio", "Pablo", "Andres", "Luis", "Miguel", "Rodrigo", "Nicolas",
                    "Facundo", "Matias", "Gonzalo", "Federico", "Emiliano", "Santiago", "Alejandro", "Ivan"],
        "apellidos": ["Rodriguez", "Gonzalez", "Fernandez", "Lopez", "Martinez", "Perez", "Garcia", "Sanchez",
                       "Romero", "Alvarez", "Silva", "Rojas", "Castro", "Vega", "Torres", "Herrera", "Aguirre",
                       "Molina", "Cabrera", "Suarez"]
    },
    "UEFA": {
        "nombres": ["Lucas", "Marco", "Andre", "Thomas", "Michael", "David", "Jan", "Erik", "Robert", "Antoine",
                     "Kevin", "Julian", "Marco", "Nikola", "Marcus", "Oliver", "Henrik", "Piotr", "Sergei", "Milan"],
        "apellidos": ["Muller", "Schmidt", "Johansson", "Kowalski", "Novak", "Hansen", "Rossi", "Dubois", "Silva",
                       "Ivanov", "Petersen", "Berg", "Fischer", "Weber", "Nowak", "Kovac", "Andersson", "Lopez",
                       "Marchetti", "Kaminski"]
    },
    "CONCACAF": {
        "nombres": ["Miguel", "Alejandro", "Rafael", "Jonathan", "Christian", "Daniel", "Tyler", "Kyle", "Andre",
                     "Marcus", "Kevin", "Diego", "Luis", "Carlos", "Ronaldo", "Devon", "Junior", "Emilio"],
        "apellidos": ["Hernandez", "Garcia", "Martinez", "Johnson", "Williams", "Brown", "Perez", "Ramirez",
                       "Torres", "Reid", "Powell", "Campbell", "Rodriguez", "Cruz", "Vargas", "Mendez"]
    },
    "CAF": {
        "nombres": ["Mohamed", "Amine", "Yassine", "Youssef", "Karim", "Omar", "Kwame", "Kofi", "Sadio", "Ismael",
                     "Cheikh", "Riyad", "Achraf", "Hakim", "Andre", "Victor", "Samuel", "Thabo", "Percy", "Bongani"],
        "apellidos": ["Diallo", "Toure", "Kone", "Traore", "Ndiaye", "Salah", "Mane", "Osimhen", "Mahrez",
                       "Hakimi", "Mendy", "Benatia", "Ziyech", "Aubameyang", "Adebayor", "Boateng", "Essien"]
    },
    "AFC": {
        "nombres": ["Takumi", "Hiroshi", "Kaoru", "Wataru", "Ali", "Hassan", "Ahmed", "Omar", "Min-jae", "Heung-min",
                     "Jae-sung", "Wu", "Zhang", "Li", "Nguyen", "Tran", "Aziz", "Bakhtiyor"],
        "apellidos": ["Tanaka", "Suzuki", "Yamamoto", "Ito", "Kim", "Lee", "Park", "Choi", "Wang", "Chen", "Liu",
                       "Ali", "Al-Faraj", "Al-Otaibi", "Reza", "Hosseini", "Karimov", "Nazarov"]
    },
    "OFC": {
        "nombres": ["Chris", "James", "Ryan", "Liam", "Kaia", "Roy", "Mateo", "Winston", "Sione", "Tama"],
        "apellidos": ["Wood", "Reid", "Boyens", "Rufer", "Smith", "Kalounivale", "Kaltak", "Bako", "Sae",
                       "Roimata", "Ihaia", "Nakauta"]
    },
}

POSICIONES_PLANTEL = (
    ["Arquero"] * 2 +          # 2 arqueros
    ["Defensor"] * 5 +         # 5 defensores
    ["Mediocampista"] * 5 +    # 5 mediocampistas
    ["Delantero"] * 4          # 4 delanteros
)  # total 16 por equipo -> 16 * 64 = 1024 jugadores

def rango_altura(pos):
    if pos == "Arquero":   return (185, 200)
    if pos == "Defensor":  return (175, 195)
    if pos == "Mediocampista": return (168, 188)
    return (168, 190)  # Delantero

def rango_peso(pos):
    if pos == "Arquero":   return (78, 95)
    if pos == "Defensor":  return (72, 90)
    if pos == "Mediocampista": return (68, 85)
    return (70, 88)

def slug(n=6):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

def fecha_iso(d: date) -> str:
    """Fecha en formato ISO 8601 con hora 00:00:00 UTC, para que mongosh la parsee como Date."""
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).isoformat()

# =============================================================================
# Construccion de documentos de equipos
# =============================================================================
hoy_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
equipos = []
for codigo, nombre, conf, ranking, sede, dt_nombre, dt_nac, colores in EQUIPOS_BASE:
    equipos.append({
        "codigo": codigo,
        "nombre": nombre,
        "confederacion": conf,
        "rankingFIFA": ranking,
        "sedeBase": sede,
        "anfitrion": codigo in ANFITRIONES,
        "colores": colores,
        "directorTecnico": {
            "nombre": dt_nombre,
            "nacionalidad": dt_nac
        },
        "fechaActualizacion": hoy_iso
    })

# =============================================================================
# Construccion de documentos de jugadores
# =============================================================================
jugadores = []
dorsales_usados = {}  # (equipoCodigo) -> set de dorsales

for equipo in equipos:
    cod_eq = equipo["codigo"]
    conf = equipo["confederacion"]
    banco_nombres = NOMBRES_POR_CONFEDERACION[conf]["nombres"]
    banco_apellidos = NOMBRES_POR_CONFEDERACION[conf]["apellidos"]

    posiciones = POSICIONES_PLANTEL.copy()
    random.shuffle(posiciones)  # mezcla el orden de asignacion de dorsal <-> posicion

    dorsales = list(range(1, 30))
    random.shuffle(dorsales)
    dorsales = dorsales[:16]
    # Un arquero suele llevar el 1; se lo aseguramos al primer arquero
    idx_primer_arquero = posiciones.index("Arquero")
    if 1 in dorsales:
        # swap para que ese arquero tenga el 1
        i1 = dorsales.index(1)
        dorsales[idx_primer_arquero], dorsales[i1] = dorsales[i1], dorsales[idx_primer_arquero]
    else:
        dorsales[idx_primer_arquero] = 1

    capitan_asignado = False
    for i, pos in enumerate(posiciones):
        nombre_j = f"{random.choice(banco_nombres)} {random.choice(banco_apellidos)}"
        dorsal = dorsales[i]
        edad = random.randint(19, 36)
        year_nac = 2030 - edad
        month_nac = random.randint(1, 12)
        day_nac = random.randint(1, 28)
        alt_min, alt_max = rango_altura(pos)
        peso_min, peso_max = rango_peso(pos)

        # el capitan suele ser un veterano de campo (no arquero); asignamos al primer no-arquero >30 anios
        es_capitan = (not capitan_asignado
                       and pos != "Arquero"
                       and edad >= 30)
        if es_capitan:
            capitan_asignado = True

        # valor de mercado dependiente de edad y posicion (heuristica simple)
        base_valor = {"Delantero": 25, "Mediocampista": 20, "Defensor": 15, "Arquero": 10}[pos]
        factor_edad = max(0.2, 1.5 - abs(edad - 26) * 0.08)
        factor_ranking = max(0.3, 1.6 - equipo["rankingFIFA"] * 0.015)
        valor_mercado = round(base_valor * factor_edad * factor_ranking * random.uniform(0.5, 1.8), 1)

        jugadores.append({
            "codigo": f"{cod_eq}-{dorsal}-{slug(6)}",
            "equipoCodigo": cod_eq,
            "nombre": nombre_j,
            "posicion": pos,
            "dorsal": dorsal,
            "fechaNacimiento": fecha_iso(date(year_nac, month_nac, day_nac)),
            "altura_cm": random.randint(alt_min, alt_max),
            "peso_kg": random.randint(peso_min, peso_max),
            "pieHabil": random.choices(["derecho", "izquierdo", "ambos"], weights=[70, 25, 5])[0],
            "partidosInternacionales": random.randint(0, min(150, max(1, (edad - 18) * 8))),
            "goles": random.randint(0, 20) if pos in ("Delantero", "Mediocampista") else random.randint(0, 5),
            "capitan": es_capitan,
            "convocado": True,
            "valorMercado_millonesEUR": valor_mercado,
            "fechaActualizacion": hoy_iso
        })

    # si ningun jugador cumplio la condicion de capitan, marcamos al primer mediocampista
    if not capitan_asignado:
        for j in jugadores[-16:]:
            if j["posicion"] == "Mediocampista":
                j["capitan"] = True
                break

# =============================================================================
# Escritura de los JSON
# =============================================================================
with open("equipos.json", "w", encoding="utf-8") as f:
    json.dump(equipos, f, ensure_ascii=False, indent=2)

with open("jugadores.json", "w", encoding="utf-8") as f:
    json.dump(jugadores, f, ensure_ascii=False, indent=2)

# Resumen para consola
print(f"[OK] Generados {len(equipos)} equipos -> equipos.json")
print(f"[OK] Generados {len(jugadores)} jugadores -> jugadores.json")
print()
print("Distribucion por confederacion:")
from collections import Counter
for conf, n in sorted(Counter(e['confederacion'] for e in equipos).items()):
    print(f"  {conf:10s}: {n:2d} equipos")
print(f"\nAnfitriones ({sum(1 for e in equipos if e['anfitrion'])}):")
for e in equipos:
    if e["anfitrion"]:
        print(f"  - {e['codigo']} ({e['nombre']})")
