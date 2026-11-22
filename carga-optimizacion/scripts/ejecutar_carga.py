"""CARGA + MEDICION: ejecuta el escenario 'pico post-gol' contra la API (RF2, RF5, RF6).

No se llama directo: lo usan ejecutar_linea_base.py y
ejecutar_prueba_optimizada.py, que fijan el modo y verifican la configuracion
de la API antes de empezar. Asi las dos corridas usan EXACTAMENTE este mismo
codigo, el mismo escenario y el mismo plan; solo cambia la configuracion de la
API (cache apagada o prendida).

Modelo de carga (Clase 13: preparar, calentar, subir, sostener, observar):
  - Usuarios virtuales (hilos) en lazo cerrado: cada uno toma la siguiente
    operacion del plan, la ejecuta, espera una pausa aleatoria y repite.
  - Cada fase de config/escenario.json fija cuantos usuarios estan activos
    (con rampa lineal si inicio != fin).
  - Todas las requests pasan por la API del Hito 10 (nunca directo a la base).

Que se mide en cada operacion:
  - latencia en el CLIENTE (perf_counter alrededor de la request completa);
  - latencia DENTRO de la API (header X-Duracion-ms);
  - codigo HTTP, tipo de error, estado de cache (header X-Cache);
  - para escrituras: ventana y comentarioId devueltos (para la integridad);
  - para lecturas: cantidad de comentarios y si la respuesta es coherente.
Ademas, en paralelo: CPU/memoria de Cassandra y Redis (docker stats), de la
API y la maquina (psutil, opcional) y del propio generador.
Antes y despues: contadores de Cassandra (nodetool) y de Redis (INFO).

Corte seguro (RNF9): si en los ultimos N segundos la tasa de error o el p95
superan los umbrales del escenario, la prueba se detiene y guarda lo medido.
Ctrl+C tambien detiene de forma ordenada.
"""
from __future__ import annotations

import argparse
import collections
import csv
import gzip
import http.client
import json
import random
import threading
import time
import urllib.parse

from lib_carga import (ARCHIVO_PLAN, ARCHIVO_RESUMEN_PLAN,
                       DIR_EVIDENCIA, MuestreoRecursos, ahora_utc, cargar_config,
                       cargar_escenario, codigo_partido, contar_claves,
                       docker_disponible, escribir_json, histogramas_tabla_cassandra,
                       info_entorno, info_git, info_redis, leer_json,
                       resumen_latencias, resumen_recursos, sha256_archivo,
                       sha256_escenario,
                       stats_tabla_cassandra, versiones_productos)


# --------------------------------------------------------------------------
# Cliente HTTP minimo (stdlib), una conexion persistente por usuario virtual
# --------------------------------------------------------------------------
class ClienteHTTP:
    def __init__(self, url_base: str, timeout_s: float):
        u = urllib.parse.urlparse(url_base)
        self.host, self.port = u.hostname, u.port or 80
        self.timeout = timeout_s
        self.conn = None

    def _conectar(self):
        self.conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)

    def request(self, metodo: str, ruta: str, cuerpo: dict | None = None):
        """Devuelve (status, headers, json|None, latencia_ms, error|None)."""
        if self.conn is None:
            self._conectar()
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        cabeceras = {"Content-Type": "application/json"} if datos else {}
        t0 = time.perf_counter()
        try:
            self.conn.request(metodo, ruta, body=datos, headers=cabeceras)
            resp = self.conn.getresponse()
            crudo = resp.read()
            lat = (time.perf_counter() - t0) * 1000
            try:
                js = json.loads(crudo) if crudo else None
            except ValueError:
                js = None
            return resp.status, dict(resp.getheaders()), js, lat, None
        except TimeoutError:
            err = "timeout_cliente"
        except (ConnectionError, http.client.HTTPException, OSError) as e:
            err = f"conexion:{e.__class__.__name__}"
        lat = (time.perf_counter() - t0) * 1000
        try:
            self.conn.close()
        finally:
            self.conn = None
        return None, {}, None, lat, err


# --------------------------------------------------------------------------
# Verificaciones previas
# --------------------------------------------------------------------------
def verificar_api(cfg: dict, etiqueta: str, cache_esperada: str, timeout: float) -> dict:
    """Comprueba que la API responde y que su cache esta como el modo espera.

    Usa un partido de verificacion propio de la corrida ('...-CHK'), solo lectura.
      cache_esperada=OFF -> la API debe responder X-Cache: OFF
      cache_esperada=ON  -> 1ra lectura MISS y 2da lectura HIT
    """
    # /salud chequea las 6 fuentes EN SERIE: las que no estan levantadas (Mongo,
    # Neo4j, InfluxDB, IRIS no hacen falta en este hito) tardan su timeout cada
    # una. Por eso /salud usa una espera larga y no la del escenario.
    st, _, js, _, err = ClienteHTTP(cfg["API_URL"], 60).request("GET", "/salud")
    if st is None:
        raise SystemExit(f"La API no responde en {cfg['API_URL']} ({err}). Verificar que "
                         "uvicorn este corriendo en la terminal A (PASO_A_PASO.md, paso 4).")
    cli = ClienteHTTP(cfg["API_URL"], timeout)
    fuentes = {d["fuente"]: d["disponible"] for d in (js or {}).get("dependencias", [])} \
        if isinstance(js, dict) else {}
    for f in ("cassandra", "redis"):
        if fuentes and not fuentes.get(f):
            raise SystemExit(f"/salud informa que {f} no esta disponible. Levantar el contenedor.")

    ruta = f"/partidos/{codigo_partido(etiqueta, 'CHK')}/comentarios?limit=20"
    st1, h1, _, _, err1 = cli.request("GET", ruta)
    st2, h2, _, _, err2 = cli.request("GET", ruta)
    if st1 != 200 or st2 != 200:
        raise SystemExit(f"GET de verificacion fallo: {st1 or err1} / {st2 or err2}")
    c1, c2 = h1.get("x-cache") or h1.get("X-Cache"), h2.get("x-cache") or h2.get("X-Cache")
    if c1 is None:
        raise SystemExit("La API no devuelve el header X-Cache: no tiene los cambios del "
                         "Hito 12. Reiniciar la API desde el commit actual.")
    if cache_esperada == "OFF" and (c1, c2) != ("OFF", "OFF"):
        raise SystemExit(f"Se esperaba cache APAGADA y la API respondio {c1}/{c2}. "
                         "Reiniciar la API con CACHE_COMENTARIOS_TTL_S=0.")
    if cache_esperada == "ON" and (c1, c2) != ("MISS", "HIT"):
        raise SystemExit(f"Se esperaba cache PRENDIDA (MISS luego HIT) y la API respondio "
                         f"{c1}/{c2}. Reiniciar la API con CACHE_COMENTARIOS_TTL_S=2.")
    return {"salud": fuentes, "verificacion_cache": [c1, c2]}


def modo_cliente_cassandra() -> str:
    """Indicio del cliente que usa la API: driver nativo o cqlsh (ver adaptador).

    La API usa el driver nativo si 'cassandra.cluster' importa. Si el generador
    corre con el MISMO Python/entorno que la API (lo que indica el README), este
    chequeo refleja lo que usa la API. Es un indicio, no una medicion: el log de
    la API ('modo=driver' / 'modo=cqlsh') es la confirmacion.
    """
    try:
        from cassandra.cluster import Cluster  # noqa: F401
        return "driver (indicio)"
    except Exception:
        return "cqlsh (indicio)"


# --------------------------------------------------------------------------
# Ejecucion de la carga
# --------------------------------------------------------------------------
class Prueba:
    def __init__(self, cfg, esc, plan, etiqueta, escala, timeout_s):
        self.cfg, self.esc, self.plan = cfg, esc, plan
        self.etiqueta, self.escala, self.timeout = etiqueta, escala, timeout_s
        self.fases = esc["fases"]
        self.limit = esc["limit_lectura"]
        self.pausa = esc["pausa_entre_operaciones_s"]
        self.registros: list[dict] = []
        self.lock_plan = threading.Lock()
        self.lock_reg = threading.Lock()
        self.siguiente = 0
        self.objetivo_usuarios = 0
        self.fase_actual = self.fases[0]["nombre"]
        self.fin = threading.Event()
        self.motivo_fin = "completa"
        self.t0 = 0.0

    def _tomar_operacion(self):
        with self.lock_plan:
            if self.siguiente >= len(self.plan):
                self.motivo_fin = "plan agotado (aumentar operaciones_en_el_plan)"
                self.fin.set()
                return None
            op = self.plan[self.siguiente]
            self.siguiente += 1
            return op

    def _ejecutar(self, cli: ClienteHTTP, op: dict, fase: str) -> dict:
        partido = codigo_partido(self.etiqueta, op["partido"])
        t_rel = time.perf_counter() - self.t0
        reg = {"i": op["i"], "fase": fase, "tipo": op["tipo"], "partido": op["partido"],
               "t_s": round(t_rel, 3)}
        if op["tipo"] == "lectura":
            st, h, js, lat, err = cli.request(
                "GET", f"/partidos/{partido}/comentarios?limit={self.limit}")
            reg["x_cache"] = h.get("x-cache") or h.get("X-Cache") or ""
            if st == 200:
                coms = (js or {}).get("comentarios")
                # HTTP 200 no alcanza: la respuesta tiene que ser del partido
                # pedido y respetar el limit.
                if (not isinstance(coms, list) or (js or {}).get("partido") != partido
                        or len(coms) > self.limit):
                    err = "respuesta_inconsistente"
                reg["n_comentarios"] = len(coms) if isinstance(coms, list) else ""
        else:
            cuerpo = {"usuarioId": op["usuarioId"], "contenido": op["contenido"],
                      "comentarioId": op["comentarioId"]}
            st, h, js, lat, err = cli.request("POST", f"/partidos/{partido}/comentarios", cuerpo)
            reg["comentario_id"] = op["comentarioId"]
            if st == 201:
                if (js or {}).get("comentarioId") != op["comentarioId"] or \
                        (js or {}).get("partido") != partido:
                    err = "respuesta_inconsistente"
                reg["ventana"] = (js or {}).get("ventana", "")
        reg["status"] = st if st is not None else ""
        if err is None and st not in (200, 201):
            err = f"http_{st}"
        reg["error"] = err or ""
        reg["ok"] = 1 if not err else 0
        reg["latencia_ms"] = round(lat, 2)
        dur_api = h.get("x-duracion-ms") or h.get("X-Duracion-ms")
        reg["api_ms"] = dur_api if dur_api is not None else ""
        return reg

    def _usuario_virtual(self, n: int):
        cli = ClienteHTTP(self.cfg["API_URL"], self.timeout)
        rng = random.Random(self.esc["semilla"] * 1000 + n)
        while not self.fin.is_set():
            if n >= self.objetivo_usuarios:
                time.sleep(0.05)
                continue
            op = self._tomar_operacion()
            if op is None:
                break
            reg = self._ejecutar(cli, op, self.fase_actual)
            with self.lock_reg:
                self.registros.append(reg)
            time.sleep(rng.uniform(self.pausa["min"], self.pausa["max"]))

    def _controlador(self):
        """Ajusta la cantidad de usuarios activos segundo a segundo, por fase."""
        for fase in self.fases:
            if self.fin.is_set():
                return
            self.fase_actual = fase["nombre"]
            print(f"  fase {fase['nombre']:<14} {fase['duracion_s']:>4}s  "
                  f"usuarios {fase['usuarios_inicio']}->{fase['usuarios_fin']} (x{self.escala})")
            inicio = time.perf_counter()
            while not self.fin.is_set():
                trans = time.perf_counter() - inicio
                if trans >= fase["duracion_s"]:
                    break
                frac = trans / fase["duracion_s"]
                u = fase["usuarios_inicio"] + (fase["usuarios_fin"] - fase["usuarios_inicio"]) * frac
                self.objetivo_usuarios = max(1, round(u * self.escala))
                time.sleep(0.25)
        self.fin.set()

    def _vigia(self):
        """Corte seguro: mira los ultimos N segundos y detiene si se degrada."""
        cs = self.esc["corte_seguro"]
        while not self.fin.wait(2):
            limite = time.perf_counter() - self.t0 - cs["ventana_s"]
            with self.lock_reg:
                recientes = [r for r in self.registros[-5000:] if r["t_s"] >= limite]
            if len(recientes) < 20:
                continue
            tasa = 1 - sum(r["ok"] for r in recientes) / len(recientes)
            p95 = resumen_latencias([r["latencia_ms"] for r in recientes]).get("p95", 0)
            if tasa > cs["max_tasa_error"] or p95 > cs["max_p95_ms"]:
                self.motivo_fin = (f"interrumpida por corte seguro: tasa_error={tasa:.2f}, "
                                   f"p95={p95:.0f} ms en los ultimos {cs['ventana_s']} s")
                print("  !! " + self.motivo_fin)
                self.fin.set()

    def correr(self):
        max_usuarios = max(max(f["usuarios_inicio"], f["usuarios_fin"]) for f in self.fases)
        max_usuarios = max(1, round(max_usuarios * self.escala))
        self.t0 = time.perf_counter()
        hilos = [threading.Thread(target=self._usuario_virtual, args=(n,), daemon=True)
                 for n in range(max_usuarios)]
        for h in hilos:
            h.start()
        ctrl = threading.Thread(target=self._controlador, daemon=True)
        vigia = threading.Thread(target=self._vigia, daemon=True)
        ctrl.start()
        vigia.start()
        try:
            while not self.fin.wait(5):
                with self.lock_reg:
                    n = len(self.registros)
                    errores = sum(1 for r in self.registros if not r["ok"])
                print(f"    t={time.perf_counter() - self.t0:6.0f}s  operaciones={n}  errores={errores}")
        except KeyboardInterrupt:
            self.motivo_fin = "interrumpida por el usuario (Ctrl+C)"
            self.fin.set()
        # Esperar a que terminen las requests en vuelo (no se cortan a la mitad)
        for h in hilos:
            h.join(timeout=self.timeout + 2)
        return time.perf_counter() - self.t0


# --------------------------------------------------------------------------
# Resumen de metricas (RF5, RF6, RNF5)
# --------------------------------------------------------------------------
def resumir(registros: list[dict], fases: list[dict], duraciones: dict,
            pausa: dict, escala: float = 1.0) -> dict:
    def bloque(regs: list[dict], segundos: float | None) -> dict:
        ok = [r for r in regs if r["ok"]]
        errores = collections.Counter(r["error"] for r in regs if not r["ok"])
        api = [float(r["api_ms"]) for r in ok if r.get("api_ms") not in ("", None)]
        brecha = [r["latencia_ms"] - float(r["api_ms"]) for r in ok
                  if r.get("api_ms") not in ("", None)]
        cache = collections.Counter(r.get("x_cache") for r in regs if r["tipo"] == "lectura")
        hits, miss = cache.get("HIT", 0), cache.get("MISS", 0)
        b = {
            "operaciones": len(regs),
            "exitosas": len(ok),
            "errores": len(regs) - len(ok),
            "tasa_error": round((len(regs) - len(ok)) / len(regs), 4) if regs else None,
            "errores_por_tipo": dict(errores),
            "latencia_cliente_ms": resumen_latencias([r["latencia_ms"] for r in ok]),
            "latencia_api_ms": resumen_latencias(api),
            "brecha_cliente_menos_api_ms": resumen_latencias(brecha),
            "cache_lecturas": dict(cache),
            "tasa_acierto_cache": round(hits / (hits + miss), 4) if (hits + miss) else None,
        }
        if segundos:
            b["segundos"] = round(segundos, 1)
            b["throughput_exitosas_por_s"] = round(len(ok) / segundos, 1)
        return b

    medidas = [f["nombre"] for f in fases if f.get("medir")]
    res = {"por_fase": {}, "medido_total": {}, "medido_por_tipo": {}}
    for f in fases:
        regs = [r for r in registros if r["fase"] == f["nombre"]]
        if regs:
            res["por_fase"][f["nombre"]] = bloque(regs, duraciones.get(f["nombre"]))
    medidos = [r for r in registros if r["fase"] in medidas]
    seg_medidos = sum(duraciones.get(n, 0) for n in medidas)
    res["medido_total"] = bloque(medidos, seg_medidos)
    for tipo, filtro in (("lectura", {"lectura"}), ("escritura", {"escritura", "reintento"})):
        res["medido_por_tipo"][tipo] = bloque([r for r in medidos if r["tipo"] in filtro],
                                              seg_medidos)
    # El generador como posible cuello de botella (Clase 13): en lazo cerrado,
    # cada usuario deberia producir ~ 1 / (pausa media + latencia media) ops/s.
    sost = res["por_fase"].get("sostenimiento")
    fase_s = next((f for f in fases if f["nombre"] == "sostenimiento"), None)
    if sost and fase_s and sost["latencia_cliente_ms"].get("n"):
        pausa_media = (pausa["min"] + pausa["max"]) / 2
        lat_media = sost["latencia_cliente_ms"]["promedio"] / 1000
        esperado = round(fase_s["usuarios_fin"] * escala) / (pausa_media + lat_media)
        res["control_generador"] = {
            "ops_por_s_observadas_sostenimiento": round(sost["operaciones"] / sost["segundos"], 1),
            "ops_por_s_esperadas_lazo_cerrado": round(esperado, 1),
        }
    return res


def duraciones_reales(registros: list[dict]) -> dict:
    """Segundos reales de cada fase (primer a ultimo inicio de operacion)."""
    por_fase = collections.defaultdict(list)
    for r in registros:
        por_fase[r["fase"]].append(r["t_s"])
    return {f: max(0.001, max(ts) - min(ts)) for f, ts in por_fase.items()}


def serie_por_segundo(registros: list[dict]) -> list[dict]:
    seg = collections.defaultdict(list)
    for r in registros:
        seg[int(r["t_s"])].append(r)
    filas = []
    for s in sorted(seg):
        regs = seg[s]
        ok = [r["latencia_ms"] for r in regs if r["ok"]]
        lat = resumen_latencias(ok)
        filas.append({"segundo": s, "fase": regs[0]["fase"], "operaciones": len(regs),
                      "exitosas": len(ok), "errores": len(regs) - len(ok),
                      "p50_ms": lat.get("p50", ""), "p95_ms": lat.get("p95", ""),
                      "p99_ms": lat.get("p99", "")})
    return filas


def resumen_markdown(meta: dict, res: dict) -> str:
    L = [f"# Corrida `{meta['etiqueta']}` ({meta['modo']})", "",
         f"- Fecha (UTC): {meta['inicio_utc']} -> {meta['fin_utc']}",
         f"- Commit: `{meta['git']['commit']}` "
         f"(cambios sin commitear en codigo: {meta['git']['cambios_sin_commitear_en_codigo']})",
         f"- Cache de la API: {meta['cache_esperada']} "
         f"(verificacion: {meta['verificacion_api']['verificacion_cache']})",
         f"- Cliente Cassandra de la API: {meta['cliente_cassandra']}",
         f"- Escenario: `{meta['escenario']['nombre']}` sha256 `{meta['escenario_sha256'][:12]}`; "
         f"plan sha256 `{meta['plan_sha256'][:12]}`; escala de usuarios x{meta['escala']}",
         f"- Fin: **{meta['motivo_fin']}**", "",
         "## Fases medidas (sin calentamiento)", "",
         "Latencias en ms medidas en el cliente (generador), solo operaciones exitosas.", "",
         "| Fase | Ops | Exitosas | Errores | Tasa err. | Ops ok/s | p50 | p95 | p99 | max | Acierto cache |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    filas = list(res["por_fase"].items()) + [("**TOTAL MEDIDO**", res["medido_total"])]
    for nombre, b in filas:
        lat = b["latencia_cliente_ms"]
        L.append(f"| {nombre} | {b['operaciones']} | {b['exitosas']} | {b['errores']} | "
                 f"{b['tasa_error']} | {b.get('throughput_exitosas_por_s', '')} | "
                 f"{lat.get('p50', '')} | {lat.get('p95', '')} | {lat.get('p99', '')} | "
                 f"{lat.get('max', '')} | {b['tasa_acierto_cache']} |")
    L += ["", "## Por tipo de operacion (fases medidas)", "",
          "| Tipo | Ops | Tasa err. | Cliente p50 | Cliente p95 | Cliente p99 | API p50 | API p95 | Brecha p95 |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for tipo, b in res["medido_por_tipo"].items():
        c, a, g = b["latencia_cliente_ms"], b["latencia_api_ms"], b["brecha_cliente_menos_api_ms"]
        L.append(f"| {tipo} | {b['operaciones']} | {b['tasa_error']} | {c.get('p50', '')} | "
                 f"{c.get('p95', '')} | {c.get('p99', '')} | {a.get('p50', '')} | "
                 f"{a.get('p95', '')} | {g.get('p95', '')} |")
    L += ["", "*Brecha = latencia en el cliente - tiempo dentro de la API (red local, cola de "
          "conexiones, serializacion HTTP y el propio generador).*", ""]
    if res.get("errores_por_tipo_total"):
        L += [f"Errores por tipo: `{res['errores_por_tipo_total']}`", ""]
    if res.get("control_generador"):
        L += ["## Control del generador", "",
              f"`{json.dumps(res['control_generador'])}`", ""]
    cas = meta.get("cassandra_delta", {})
    L += ["## Lo que llego a Cassandra (nodetool, diferencia antes/despues)", "",
          f"`{json.dumps(cas, ensure_ascii=False)}`", "",
          "## Redis (INFO, antes -> despues)", "",
          f"`{json.dumps(meta.get('redis_delta', {}), ensure_ascii=False)}`", "",
          "## Recursos (promedio / maximo)", "", "| Medida | Promedio | Max | Muestras |",
          "|---|---:|---:|---:|"]
    for k, v in meta.get("recursos", {}).items():
        L.append(f"| {k} | {v['promedio']} | {v['max']} | {v['muestras']} |")
    if meta.get("notas"):
        L += ["", "## Notas de medicion", ""] + [f"- {n}" for n in meta["notas"]]
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
# Programa principal
# --------------------------------------------------------------------------
def main(argv=None) -> str:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--modo", required=True, choices=["base", "opt"])
    ap.add_argument("--cache-esperada", required=True, choices=["OFF", "ON"])
    ap.add_argument("--etiqueta", help="nombre de la corrida (por defecto modo-fecha)")
    ap.add_argument("--escala", type=float, default=1.0,
                    help="multiplica los usuarios de cada fase (bajar a 0.5 si la notebook no da)")
    ap.add_argument("--sin-docker", action="store_true",
                    help="no medir con docker (stats, nodetool, redis-cli)")
    a = ap.parse_args(argv)

    cfg, esc = cargar_config(), cargar_escenario()
    if not ARCHIVO_PLAN.exists():
        raise SystemExit("Falta datos/plan.jsonl. Ejecutar primero: python scripts/preparar_datos.py")
    resumen_plan = leer_json(ARCHIVO_RESUMEN_PLAN)
    if sha256_archivo(ARCHIVO_PLAN) != resumen_plan["plan_sha256"]:
        raise SystemExit("plan.jsonl no coincide con resumen_plan.json. Regenerar el plan.")
    if resumen_plan["escenario_sha256"] != sha256_escenario():
        raise SystemExit("escenario.json cambio desde que se genero el plan. Regenerar el plan.")
    with open(ARCHIVO_PLAN, encoding="utf-8") as f:
        plan = [json.loads(l) for l in f]

    etiqueta = a.etiqueta or f"{a.modo}-{ahora_utc().strftime('%Y%m%d-%H%M%S')}"
    destino = DIR_EVIDENCIA / etiqueta
    if destino.exists():
        raise SystemExit(f"Ya existe {destino}. Usar otra --etiqueta (no se pisa evidencia).")
    usar_docker = not a.sin_docker and docker_disponible()
    notas = [] if usar_docker else ["mediciones de docker omitidas (--sin-docker o docker no disponible)"]

    print(f"== Hito 12 | corrida {etiqueta} | cache esperada {a.cache_esperada}")
    verif = verificar_api(cfg, etiqueta, a.cache_esperada, esc["timeout_cliente_s"])
    print(f"  API ok, cache verificada: {verif['verificacion_cache']}")

    antes = {}
    if usar_docker:
        print("  tomando contadores previos (nodetool / redis INFO)...")
        antes = {"cassandra": stats_tabla_cassandra(cfg), "redis": info_redis(cfg),
                 "sesiones": contar_claves(cfg, "sesion:*")}

    inicio = ahora_utc()
    prueba = Prueba(cfg, esc, plan, etiqueta, a.escala, esc["timeout_cliente_s"])
    muestreo = MuestreoRecursos(cfg, esc["muestreo_recursos_s"], time.perf_counter(), usar_docker)
    muestreo.t0 = time.perf_counter()
    muestreo.start()
    duracion = prueba.correr()
    muestreo.detener.set()
    fin = ahora_utc()
    print(f"  fin: {prueba.motivo_fin} ({duracion:.0f} s, {len(prueba.registros)} operaciones)")

    despues, histos = {}, {}
    if usar_docker:
        print("  tomando contadores posteriores...")
        despues = {"cassandra": stats_tabla_cassandra(cfg), "redis": info_redis(cfg),
                   "sesiones": contar_claves(cfg, "sesion:*")}
        try:
            histos = histogramas_tabla_cassandra(cfg)
        except Exception as e:
            notas.append(f"nodetool tablehistograms no disponible: {e}")

    def delta(k, base="cassandra"):
        try:
            return float(despues[base][k]) - float(antes[base][k])
        except (KeyError, TypeError, ValueError):
            return None

    regs = sorted(prueba.registros, key=lambda r: r["t_s"])
    res = resumir(regs, esc["fases"], duraciones_reales(regs), esc["pausa_entre_operaciones_s"],
                  a.escala)
    res["errores_por_tipo_total"] = dict(collections.Counter(r["error"] for r in regs if r["error"]))

    meta = {
        "etiqueta": etiqueta, "modo": a.modo, "cache_esperada": a.cache_esperada,
        "inicio_utc": inicio.isoformat(), "fin_utc": fin.isoformat(),
        "duracion_s": round(duracion, 1), "motivo_fin": prueba.motivo_fin,
        "escala": a.escala, "escenario": esc,
        "escenario_sha256": resumen_plan["escenario_sha256"],
        "plan_sha256": resumen_plan["plan_sha256"],
        "operaciones_consumidas_del_plan": prueba.siguiente,
        "partidos_de_la_corrida": {p["clave"]: codigo_partido(etiqueta, p["clave"])
                                   for p in esc["partidos"]},
        "api_url": cfg["API_URL"], "verificacion_api": verif,
        "cliente_cassandra": modo_cliente_cassandra(),
        "git": info_git(), "entorno": info_entorno(),
        "versiones": versiones_productos(cfg) if usar_docker else {},
        "contadores_antes": antes, "contadores_despues": despues,
        "cassandra_delta": {
            "lecturas_que_llegaron_a_cassandra": delta("lecturas_locales"),
            "escrituras_que_llegaron_a_cassandra": delta("escrituras_locales"),
            "latencia_local_despues": {k: despues.get("cassandra", {}).get(k) for k in
                                       ("latencia_lectura_local_ms", "latencia_escritura_local_ms")},
            "percentiles_locales_us": histos,
        } if usar_docker else {},
        "redis_delta": {
            "evicted_keys": delta("evicted_keys", "redis"),
            "keyspace_hits": delta("keyspace_hits", "redis"),
            "keyspace_misses": delta("keyspace_misses", "redis"),
            "used_memory_antes": antes.get("redis", {}).get("used_memory_human"),
            "used_memory_despues": despues.get("redis", {}).get("used_memory_human"),
            "maxmemory_policy": despues.get("redis", {}).get("maxmemory_policy"),
            "claves_sesion_antes": antes.get("sesiones"),
            "claves_sesion_despues": despues.get("sesiones"),
        } if usar_docker else {},
        "recursos": resumen_recursos(muestreo.muestras),
        "notas": notas + muestreo.notas,
    }

    destino.mkdir(parents=True)
    escribir_json(destino / "metadata.json", meta)
    escribir_json(destino / "resumen.json", res)
    campos = ["i", "fase", "tipo", "partido", "t_s", "status", "ok", "error", "latencia_ms",
              "api_ms", "x_cache", "n_comentarios", "comentario_id", "ventana"]
    with gzip.open(destino / "operaciones.csv.gz", "wt", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(regs)
    with open(destino / "serie_por_segundo.csv", "w", encoding="utf-8", newline="") as f:
        filas = serie_por_segundo(regs)
        if filas:
            w = csv.DictWriter(f, fieldnames=list(filas[0]))
            w.writeheader()
            w.writerows(filas)
    with open(destino / "recursos.csv", "w", encoding="utf-8", newline="") as f:
        claves = sorted({k for m in muestreo.muestras for k in m}, key=lambda k: (k != "t", k))
        if claves:
            w = csv.DictWriter(f, fieldnames=claves)
            w.writeheader()
            w.writerows(muestreo.muestras)
    (destino / "resumen.md").write_text(resumen_markdown(meta, res), encoding="utf-8")

    t = res["medido_total"]
    print(f"\n  RESULTADO (fases medidas): {t['exitosas']}/{t['operaciones']} exitosas, "
          f"{t.get('throughput_exitosas_por_s')} ops/s, "
          f"p50={t['latencia_cliente_ms'].get('p50')} ms, p95={t['latencia_cliente_ms'].get('p95')} ms, "
          f"p99={t['latencia_cliente_ms'].get('p99')} ms")
    print(f"  Evidencia en: {destino}")
    print(f"  Siguiente paso: python scripts/validar_integridad.py {etiqueta}")
    return etiqueta


if __name__ == "__main__":
    main()
