"""Simulador de un partido en vivo contra la API integrada (demo final, Hito 13).

Que hace: juega un partido de LABORATORIO completo, en tiempo comprimido, con
hinchas virtuales que generan trafico real sobre las seis bases. Todo pasa por
la API (nunca va directo a una base), asi Prometheus y Grafana lo ven igual que
el trafico del Hito 13.

  Arbitro (1 hilo)   crea el partido (IRIS + Neo4j + Redis), lo inicia, mueve el
                     reloj (Redis), escribe 1 punto por segundo por equipo
                     (InfluxDB) y registra goles y tarjetas (IRIS decide; Neo4j
                     conecta). Al final del partido intenta un gol con el partido
                     Finalizado: IRIS tiene que rechazarlo (409).
  Hinchas (N hilos)  inician sesion (Redis Hash con TTL + HyperLogLog del
                     partido) y en lazo cerrado leen el feed (Cassandra via cache
                     Redis), comentan (Cassandra), renuevan la sesion (Redis),
                     miran fichas (MongoDB), eventos (Neo4j) y el tablero (las 6).
                     Despues de cada gol, durante 1 minuto de juego, comentan 4
                     veces mas: es el "pico de gol" del Hito 1.

Escenario por defecto (supuesto de laboratorio, NO un dato oficial):
  Partido inaugural del Centenario, 8 de junio de 2030, Estadio Centenario
  (Montevideo): Uruguay vs Argentina, la final de 1930. FIFA confirmo la sede y
  la fecha de la celebracion; el rival es un supuesto del grupo.

Honestidad (RNF8): con 40 hinchas en una notebook se mide el COMPORTAMIENTO del
sistema (latencia, aislamiento, cache, picos), no la escala de 2-3 M de
usuarios, que sigue siendo proyeccion.

Integridad (RNF5): solo escribe sobre el partido H13-DEMO-... (laboratorio).

Uso (desde la raiz del repositorio, con la API levantada):
  .\\monitoreo\\scripts\\simular_partido_en_vivo.ps1                       # 90' en ~3 min
  .\\monitoreo\\scripts\\simular_partido_en_vivo.ps1 --hinchas 60 --segundos-por-minuto 1
  ./monitoreo/scripts/simular_partido_en_vivo.sh --sin-evidencia
"""
from __future__ import annotations

import argparse
import collections
import csv
import gzip
import http.client
import json
import random
import sys
import threading
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_monitoreo import (DIR_EVIDENCIA, escribir_json, escribir_texto,  # noqa: E402
                           etiqueta_nueva, info_git)

FRASES = ["Vamos que se puede", "Que jugada!", "Esto es un Mundial", "100 anos de historia",
          "Arbitro, era falta", "Ese arquero es una pared", "Tremendo partido",
          "Se viene el segundo", "Dale, dale", "Asi se juega", "No lo puedo creer",
          "Centenario lleno", "Que atajada", "Presionen mas arriba", "Golazo de otro planeta"]

# (accion, base(s), peso). Pesos parecidos a la mezcla del Hito 13: el feed
# concentra la carga; el resto mantiene vivas las otras bases.
MEZCLA = [
    ("leer_feed", "cassandra+redis", 0.42),
    ("comentar", "cassandra", 0.20),
    ("renovar_sesion", "redis", 0.10),
    ("ficha_equipo", "mongodb", 0.09),
    ("eventos", "neo4j", 0.09),
    ("tablero", "las 6", 0.06),
    ("plantel", "mongodb", 0.04),
]


class Cliente:
    """Una conexion HTTP keep-alive por hilo (como un navegador)."""

    def __init__(self, base: str, timeout: float = 10.0):
        u = urllib.parse.urlparse(base)
        self.host, self.port, self.timeout = u.hostname, u.port or 80, timeout
        self.conn = None

    def pedir(self, metodo: str, ruta: str, cuerpo=None):
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        cab = {"Content-Type": "application/json"} if datos else {}
        for intento in (1, 2):
            try:
                if self.conn is None:
                    self.conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
                t0 = time.perf_counter()
                self.conn.request(metodo, ruta, body=datos, headers=cab)
                r = self.conn.getresponse()
                txt = r.read()
                ms = (time.perf_counter() - t0) * 1000
                try:
                    js = json.loads(txt) if txt else None
                except ValueError:
                    js = None
                return r.status, js, ms, {k.lower(): v for k, v in r.getheaders()}
            except (http.client.HTTPException, OSError):
                if self.conn is not None:
                    self.conn.close()
                self.conn = None
                if intento == 2:
                    return 0, None, 0.0, {}
        return 0, None, 0.0, {}


class Registro:
    """Acumula cada request (para el resumen y el CSV de evidencia)."""

    def __init__(self):
        self.filas = []
        self.lock = threading.Lock()

    def anotar(self, accion, fuente, status, ms, cab):
        with self.lock:
            self.filas.append((time.time(), accion, fuente, status, round(ms, 2),
                               cab.get("x-duracion-ms", ""), cab.get("x-cache", "")))

    def ventana(self, segundos: float):
        limite = time.time() - segundos
        with self.lock:
            return [f for f in self.filas if f[0] >= limite]


class Partido:
    """Estado compartido entre el arbitro y los hinchas."""

    def __init__(self, a):
        self.codigo, self.local, self.visit = a.codigo, a.local, a.visitante
        self.minuto, self.marcador, self.estado = 0, [0, 0], "Programado"
        self.pico_hasta = 0.0
        self.terminado = threading.Event()
        self.goles = []
        self.rechazo = None


def percentil(valores, q):
    if not valores:
        return 0.0
    v = sorted(valores)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]


# ------------------------------------------------------------------- arbitro
def arbitro(a, p: Partido, reg: Registro, planteles: dict):
    cli = Cliente(a.api)
    rnd = random.Random(a.semilla)

    def llamar(accion, fuente, metodo, ruta, cuerpo=None):
        st, js, ms, cab = cli.pedir(metodo, ruta, cuerpo)
        reg.anotar(accion, fuente, st, ms, cab)
        return st, js

    # Guion del partido: goles y tarjetas en minutos al azar (reproducible con --semilla).
    n_goles = rnd.randint(2, 4)
    guion = {m: ("Gol", rnd.choice([p.local, p.visit])) for m in rnd.sample(range(5, 89), n_goles)}
    for m in rnd.sample([x for x in range(8, 88) if x not in guion], 3):
        guion[m] = ("Tarjeta", rnd.choice([p.local, p.visit]))

    st, js = llamar("crear_partido", "iris+neo4j+redis", "POST", "/vivo/partidos",
                    {"codigo": p.codigo, "local": p.local, "visitante": p.visit,
                     "sede": a.sede, "fecha": a.fecha})
    if st != 201:
        print(f"[ERROR] no se pudo crear el partido ({st}): {js}")
        p.terminado.set()
        return
    print(f"  Partido {p.codigo} creado en IRIS (terna: "
          f"{', '.join(t['arbitro'] for t in js['partido'].get('terna', []))}) y en Neo4j")
    st, js = llamar("iniciar", "iris+redis", "POST", f"/vivo/partidos/{p.codigo}/iniciar")
    if st != 200:
        print(f"[ERROR] no se pudo iniciar ({st}): {js}")
        p.terminado.set()
        return
    p.estado = "EnJuego"
    print("  Pitazo inicial: Programado -> EnJuego (validado por IRIS)\n")

    stats = {eq: {"pases": 0, "tiros": 0, "rec": 0} for eq in (p.local, p.visit)}
    pos = 50 + rnd.uniform(-5, 5)
    for minuto in range(1, 91):
        p.minuto = minuto
        llamar("reloj", "redis", "PUT", f"/vivo/partidos/{p.codigo}/reloj", {"minuto": minuto})
        if minuto in guion:
            tipo, eq = guion[minuto]
            cand = [j for j in planteles.get(eq, []) if j.get("posicion") in ("Delantero", "Mediocampista")] \
                or planteles.get(eq, [])
            if cand:
                j = rnd.choice(cand)
                st, js = llamar(f"evento_{tipo.lower()}", "iris+neo4j+redis", "POST",
                                f"/vivo/partidos/{p.codigo}/eventos",
                                {"tipo": tipo, "minuto": minuto, "jugadorCodigo": j["codigo"]})
                if st == 201 and tipo == "Gol":
                    p.marcador = [js["partido"]["golesLocal"], js["partido"]["golesVisitante"]]
                    p.goles.append((minuto, eq, j.get("nombre") or j["codigo"]))
                    p.pico_hasta = time.time() + a.segundos_por_minuto  # 1 minuto de juego
                    print(f"  ⚽ {minuto}' GOL de {eq}: {j.get('nombre') or j['codigo']}  "
                          f"-> {p.local} {p.marcador[0]} - {p.marcador[1]} {p.visit}")
                elif st == 201:
                    print(f"  🟨 {minuto}' tarjeta para {eq}: {j.get('nombre') or j['codigo']}")
        # Estadisticas: 1 punto por segundo real por equipo (como el Hito 8).
        fin_minuto = time.time() + a.segundos_por_minuto
        while True:
            pos = max(32.0, min(68.0, pos + rnd.gauss(0, 0.8)))
            puntos = []
            for eq, ps in ((p.local, pos), (p.visit, 100 - pos)):
                s = stats[eq]
                s["pases"] += rnd.randint(0, 3)
                s["tiros"] += 1 if rnd.random() < 0.02 else 0
                s["rec"] += 1 if rnd.random() < 0.15 else 0
                puntos.append({"equipoId": eq, "posesionPct": round(ps, 1), "pasesAcum": s["pases"],
                               "tirosAcum": s["tiros"], "recuperacionesAcum": s["rec"]})
            llamar("estadisticas", "influxdb", "POST", f"/vivo/partidos/{p.codigo}/estadisticas",
                   {"sede": a.sede, "grupo": "-", "puntos": puntos})
            resto = fin_minuto - time.time()
            if resto <= 0:
                break
            time.sleep(min(1.0, resto))
        if minuto == 45:
            print("  ⏸ Entretiempo")
            p.pico_hasta = time.time() + a.entretiempo_s
            time.sleep(a.entretiempo_s)

    st, js = llamar("finalizar", "iris+redis", "POST", f"/vivo/partidos/{p.codigo}/finalizar")
    p.estado = "Finalizado" if st == 200 else p.estado
    print(f"\n  Pitazo final: {p.local} {p.marcador[0]} - {p.marcador[1]} {p.visit} (IRIS: {p.estado})")
    # La regla de IRIS en vivo: un evento con el partido Finalizado se rechaza.
    j = (planteles.get(p.local) or [{"codigo": "?"}])[0]
    st, js = llamar("gol_post_final", "iris", "POST", f"/vivo/partidos/{p.codigo}/eventos",
                    {"tipo": "Gol", "minuto": 95, "jugadorCodigo": j["codigo"]})
    p.rechazo = (st, (js or {}).get("error", {}).get("detalles", {}).get("motivo"))
    print(f"  Intento de gol con el partido Finalizado -> HTTP {st} "
          f"({'rechazado por IRIS, como debe ser' if st == 409 else 'ATENCION: no se rechazo'})")
    p.terminado.set()


# ------------------------------------------------------------------- hinchas
def hincha(n: int, a, p: Partido, reg: Registro):
    cli = Cliente(a.api)
    rnd = random.Random(a.semilla * 1000 + n)
    usuario = f"u-{n:05d}"
    st, js, ms, cab = cli.pedir("POST", "/sesiones",
                                {"usuarioId": usuario, "rol": "hincha", "partido": p.codigo})
    reg.anotar("login", "redis", st, ms, cab)
    sesion = js.get("sesionId") if st == 201 and js else None
    acciones = [x[0] for x in MEZCLA]
    pesos = [x[2] for x in MEZCLA]
    fuentes = {x[0]: x[1] for x in MEZCLA}
    while not p.terminado.is_set():
        en_pico = time.time() < p.pico_hasta
        acc = rnd.choices(acciones, weights=[w * (4 if (en_pico and x == "comentar") else 1)
                                             for x, w in zip(acciones, pesos)])[0]
        if acc == "leer_feed":
            r = cli.pedir("GET", f"/partidos/{p.codigo}/comentarios?limit=20")
        elif acc == "comentar":
            r = cli.pedir("POST", f"/partidos/{p.codigo}/comentarios",
                          {"usuarioId": usuario, "contenido": rnd.choice(FRASES)})
        elif acc == "renovar_sesion":
            if not sesion:
                continue
            r = cli.pedir("POST", f"/sesiones/{sesion}/actividad")
        elif acc == "ficha_equipo":
            r = cli.pedir("GET", f"/equipos/{rnd.choice([p.local, p.visit])}")
        elif acc == "plantel":
            r = cli.pedir("GET", f"/equipos/{rnd.choice([p.local, p.visit])}/jugadores?limit=30")
        elif acc == "eventos":
            r = cli.pedir("GET", f"/partidos/{p.codigo}/eventos")
        else:
            r = cli.pedir("GET", f"/vivo/partidos/{p.codigo}/tablero?local={p.local}"
                                 f"&visitante={p.visit}&minutos=10")
        st, _, ms, cab = r
        reg.anotar(acc, fuentes[acc], st, ms, cab)
        time.sleep(rnd.uniform(0.1, 0.3))


# ------------------------------------------------------------------- informe
def reporte(p: Partido, reg: Registro, cada: float):
    while not p.terminado.wait(cada):
        v = reg.ventana(cada)
        if not v:
            continue
        lat = [f[4] for f in v if f[3]]
        err = collections.Counter(f[3] for f in v if f[3] >= 500 or f[3] == 0)
        lect = [f for f in v if f[1] == "leer_feed" and f[6] in ("HIT", "MISS")]
        hit = 100 * sum(1 for f in lect if f[6] == "HIT") / len(lect) if lect else 0
        print(f"  [{p.minuto:>2}'] {p.local} {p.marcador[0]}-{p.marcador[1]} {p.visit} | "
              f"{len(v) / cada:6.1f} req/s | p50 {percentil(lat, .5):6.1f} ms | "
              f"p95 {percentil(lat, .95):6.1f} ms | cache {hit:5.1f} % | "
              f"5xx/sin respuesta {dict(err) or 0}")


def informe_final(a, p: Partido, reg: Registro, t_ini: float, etiqueta: str) -> str:
    filas = reg.filas
    dur = max(time.time() - t_ini, 1)
    lat = [f[4] for f in filas if f[3]]
    por_accion = collections.defaultdict(list)
    for f in filas:
        por_accion[(f[1], f[2])].append(f)
    lect = [f for f in filas if f[1] == "leer_feed" and f[6] in ("HIT", "MISS")]
    hit = 100 * sum(1 for f in lect if f[6] == "HIT") / len(lect) if lect else 0
    err5 = sum(1 for f in filas if f[3] >= 500 or f[3] == 0)
    lineas = [
        f"# Demo en vivo — partido {p.codigo} ({etiqueta})", "",
        f"- Escenario (supuesto de laboratorio): {p.local} vs {p.visit}, sede {a.sede}, {a.fecha}.",
        f"- Hinchas virtuales: {a.hinchas} en lazo cerrado (pausa 0,1-0,3 s); "
        f"{a.segundos_por_minuto} s reales por minuto de juego.",
        f"- Duracion: {dur:.0f} s · requests: {len(filas)} · **{len(filas) / dur:.1f} requests/s**",
        f"- Latencia del cliente: p50 {percentil(lat, .5):.1f} ms · **p95 {percentil(lat, .95):.1f} ms** "
        f"· p99 {percentil(lat, .99):.1f} ms",
        f"- 5xx o sin respuesta: {err5} ({100 * err5 / max(len(filas), 1):.2f} %) · "
        f"aciertos de cache del feed: {hit:.1f} %",
        f"- Resultado (IRIS): {p.local} {p.marcador[0]} - {p.marcador[1]} {p.visit} · "
        f"goles: {', '.join(f'{m} {e} {n}' for m, e, n in p.goles) or 'ninguno'}",
        f"- Gol con el partido Finalizado: HTTP {p.rechazo[0] if p.rechazo else '-'} — "
        f"{(p.rechazo or (None, ''))[1] or ''}", "",
        "| Accion | Base(s) | Requests | p50 ms | p95 ms | Errores |",
        "| :--- | :--- | ---: | ---: | ---: | ---: |"]
    for (acc, fuente), fs in sorted(por_accion.items(), key=lambda x: -len(x[1])):
        l2 = [f[4] for f in fs if f[3]]
        e = sum(1 for f in fs if f[3] >= 400 or f[3] == 0)
        lineas.append(f"| {acc} | {fuente} | {len(fs)} | {percentil(l2, .5):.1f} | "
                      f"{percentil(l2, .95):.1f} | {e} |")
    lineas += ["", "Medido en una sola maquina (API, 6 bases y monitoreo compartiendo CPU). "
                   "No demuestra 2-3 M de usuarios: eso es proyeccion (RNF8)."]
    return "\n".join(lineas) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--codigo", default="H13-DEMO-URUARG")
    ap.add_argument("--local", default="URU")
    ap.add_argument("--visitante", default="ARG")
    ap.add_argument("--sede", default="CENT")
    ap.add_argument("--fecha", default="2030-06-08")
    ap.add_argument("--hinchas", type=int, default=40, help="usuarios virtuales (Hito 12: 40 a 60)")
    ap.add_argument("--segundos-por-minuto", type=float, default=2.0,
                    help="segundos reales por minuto de juego (2 -> 90' en 3 min)")
    ap.add_argument("--entretiempo-s", type=float, default=8.0)
    ap.add_argument("--semilla", type=int, default=2030)
    ap.add_argument("--sin-evidencia", action="store_true", help="no guarda el informe")
    a = ap.parse_args()
    a.local, a.visitante, a.sede = a.local.upper(), a.visitante.upper(), a.sede.upper()

    print(f"\n=== Fixture 2030 · Demo en vivo: {a.local} vs {a.visitante} ({a.sede}, {a.fecha}) ===")
    cli = Cliente(a.api)
    st, salud, _, _ = cli.pedir("GET", "/salud")
    if st != 200:
        sys.exit(f"La API no responde en {a.api} (HTTP {st}). Levantarla con "
                 "monitoreo/scripts/iniciar_api_monitoreada.")
    caidas = [d["fuente"] for d in salud["dependencias"] if not d["disponible"]]
    print("  Bases:", ", ".join(f"{d['fuente']} {'OK' if d['disponible'] else 'CAIDA'}"
                               for d in salud["dependencias"]))
    if caidas:
        print(f"  [aviso] {', '.join(caidas)} no disponible(s): sus secciones van a dar 503 "
              "y el resto sigue (aislamiento de fallas).")
    planteles = {}
    for eq in (a.local, a.visitante):
        st, js, _, _ = cli.pedir("GET", f"/equipos/{eq}/jugadores?limit=100")
        planteles[eq] = js.get("jugadores", []) if st == 200 and js else []
        print(f"  Plantel de {eq} desde MongoDB: {len(planteles[eq])} jugadores")

    p, reg = Partido(a), Registro()
    t_ini = time.time()
    hilos = [threading.Thread(target=arbitro, args=(a, p, reg, planteles), daemon=True)]
    hilos += [threading.Thread(target=hincha, args=(i, a, p, reg), daemon=True)
              for i in range(1, a.hinchas + 1)]
    hilos.append(threading.Thread(target=reporte, args=(p, reg, 5.0), daemon=True))
    for h in hilos:
        h.start()
    try:
        while not p.terminado.wait(0.5):
            pass
    except KeyboardInterrupt:
        print("\n  Interrumpido: se cierra el partido sin finalizarlo.")
        p.terminado.set()
    time.sleep(0.5)

    etiqueta = etiqueta_nueva()
    texto = informe_final(a, p, reg, t_ini, etiqueta)
    print("\n" + texto)
    if not a.sin_evidencia:
        dir_ = DIR_EVIDENCIA / "demo_en_vivo" / etiqueta
        escribir_texto(dir_ / "resumen.md", texto)
        escribir_json(dir_ / "metadata.json", {"etiqueta": etiqueta, "parametros": vars(a),
                                               "git": info_git(), "salud_inicial": salud})
        dir_.mkdir(parents=True, exist_ok=True)
        with gzip.open(dir_ / "requests_cliente.csv.gz", "wt", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["epoch", "accion", "fuente", "http", "ms_cliente", "ms_api", "cache"])
            w.writerows(reg.filas)
        print(f"  Evidencia: {dir_}")


if __name__ == "__main__":
    main()
