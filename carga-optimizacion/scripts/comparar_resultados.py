"""COMPARACION antes/despues (RF10, RNF3).

Lee dos corridas (linea base y optimizada), verifica que sean comparables
(mismo escenario, mismo plan, misma escala, mismo cliente de Cassandra) y genera:
  docs/evidencia/comparacion.md      tablas antes/despues con la variacion
  docs/evidencia/comparacion.json    los mismos datos en JSON
  docs/evidencia/comparacion_latencias.png   (si matplotlib esta instalado)
  docs/evidencia/comparacion_p95_en_el_tiempo.png

Uso:
  python scripts/comparar_resultados.py <etiqueta_base> <etiqueta_opt>
"""
from __future__ import annotations

import csv
import sys

from lib_carga import DIR_EVIDENCIA, escribir_json, leer_json


def variacion(antes, despues) -> str:
    try:
        a, d = float(antes), float(despues)
    except (TypeError, ValueError):
        return ""
    if a == 0:
        return ""
    return f"{(d - a) / a * 100:+.1f}%"


def cargar(etiqueta: str) -> dict:
    d = DIR_EVIDENCIA / etiqueta
    datos = {"meta": leer_json(d / "metadata.json"), "res": leer_json(d / "resumen.json")}
    integ = d / "integridad.json"
    datos["integ"] = leer_json(integ) if integ.exists() else None
    with open(d / "serie_por_segundo.csv", encoding="utf-8") as f:
        datos["serie"] = list(csv.DictReader(f))
    return datos


def chequear_comparabilidad(b: dict, o: dict) -> list[str]:
    mb, mo = b["meta"], o["meta"]
    dif = []
    for clave, nombre in [("escenario_sha256", "escenario"), ("plan_sha256", "plan de datos"),
                          ("escala", "escala de usuarios"), ("cliente_cassandra", "cliente de Cassandra"),
                          ("api_url", "URL de la API")]:
        if mb.get(clave) != mo.get(clave):
            dif.append(f"distinto {nombre}: {mb.get(clave)} vs {mo.get(clave)}")
    if mb["entorno"].get("sistema") != mo["entorno"].get("sistema"):
        dif.append("distinta maquina o sistema operativo")
    if mb["git"].get("commit") != mo["git"].get("commit"):
        dif.append(f"distinto commit de codigo: {mb['git'].get('commit')} vs {mo['git'].get('commit')} "
                   "(aceptable solo si el unico cambio es documentacion)")
    for m, et in ((mb, "base"), (mo, "opt")):
        if m["git"].get("cambios_sin_commitear_en_codigo"):
            dif.append(f"la corrida {et} se hizo con cambios sin commitear en el codigo")
        if m["motivo_fin"] != "completa":
            dif.append(f"la corrida {et} no termino completa: {m['motivo_fin']}")
    return dif


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Uso: python scripts/comparar_resultados.py <etiqueta_base> <etiqueta_opt>")
    b, o = cargar(sys.argv[1]), cargar(sys.argv[2])
    dif = chequear_comparabilidad(b, o)

    filas = []

    def fila(nombre, va, vd, mejor="menor"):
        filas.append({"metrica": nombre, "linea_base": va, "optimizada": vd,
                      "variacion": variacion(va, vd), "mejor_si": mejor})

    for ambito, rb, ro in [("total medido", b["res"]["medido_total"], o["res"]["medido_total"]),
                           ("sostenimiento", b["res"]["por_fase"].get("sostenimiento", {}),
                            o["res"]["por_fase"].get("sostenimiento", {})),
                           ("pico", b["res"]["por_fase"].get("pico", {}),
                            o["res"]["por_fase"].get("pico", {})),
                           ("lecturas", b["res"]["medido_por_tipo"]["lectura"],
                            o["res"]["medido_por_tipo"]["lectura"]),
                           ("escrituras", b["res"]["medido_por_tipo"]["escritura"],
                            o["res"]["medido_por_tipo"]["escritura"])]:
        if not rb or not ro:
            continue
        fila(f"[{ambito}] operaciones", rb.get("operaciones"), ro.get("operaciones"), "mayor")
        fila(f"[{ambito}] ops exitosas/s", rb.get("throughput_exitosas_por_s"),
             ro.get("throughput_exitosas_por_s"), "mayor")
        fila(f"[{ambito}] tasa de error", rb.get("tasa_error"), ro.get("tasa_error"))
        for p in ("p50", "p95", "p99", "max"):
            fila(f"[{ambito}] latencia cliente {p} (ms)", rb["latencia_cliente_ms"].get(p),
                 ro["latencia_cliente_ms"].get(p))
        fila(f"[{ambito}] latencia API p95 (ms)", rb["latencia_api_ms"].get("p95"),
             ro["latencia_api_ms"].get("p95"))
        fila(f"[{ambito}] acierto de cache", rb.get("tasa_acierto_cache"),
             ro.get("tasa_acierto_cache"), "mayor")

    cb, co = b["meta"].get("cassandra_delta", {}), o["meta"].get("cassandra_delta", {})
    fila("lecturas que llegaron a Cassandra (nodetool)",
         cb.get("lecturas_que_llegaron_a_cassandra"), co.get("lecturas_que_llegaron_a_cassandra"))
    fila("escrituras que llegaron a Cassandra (nodetool)",
         cb.get("escrituras_que_llegaron_a_cassandra"), co.get("escrituras_que_llegaron_a_cassandra"), "-")
    rb_, ro_ = b["meta"].get("recursos", {}), o["meta"].get("recursos", {})
    for k in sorted(set(rb_) | set(ro_)):
        fila(f"recurso {k} (promedio)", rb_.get(k, {}).get("promedio"), ro_.get(k, {}).get("promedio"), "-")
        fila(f"recurso {k} (max)", rb_.get(k, {}).get("max"), ro_.get(k, {}).get("max"), "-")
    redb, redo = b["meta"].get("redis_delta", {}), o["meta"].get("redis_delta", {})
    fila("redis evicted_keys durante la prueba", redb.get("evicted_keys"), redo.get("evicted_keys"))
    fila("redis memoria usada despues", redb.get("used_memory_despues"), redo.get("used_memory_despues"), "-")

    integ = {}
    for et, d in (("linea_base", b), ("optimizada", o)):
        i = d["integ"] or {}
        integ[et] = {k: i.get(k) for k in ("veredicto", "escrituras_aceptadas_201", "perdidos",
                                            "alterados", "escritos_sin_confirmacion",
                                            "duplicados_por_reintento", "duplicados_inesperados")}

    escribir_json(DIR_EVIDENCIA / "comparacion.json",
                  {"linea_base": sys.argv[1], "optimizada": sys.argv[2],
                   "diferencias_de_condiciones": dif, "metricas": filas, "integridad": integ})

    L = ["# Comparacion linea base vs. optimizada", "",
         f"- Linea base: `{sys.argv[1]}` (commit `{b['meta']['git']['commit']}`, cache {b['meta']['cache_esperada']})",
         f"- Optimizada: `{sys.argv[2]}` (commit `{o['meta']['git']['commit']}`, cache {o['meta']['cache_esperada']})",
         f"- Escenario: `{b['meta']['escenario']['nombre']}`, escala x{b['meta']['escala']} / x{o['meta']['escala']}",
         "", "## Condiciones", ""]
    L += ([f"- ATENCION: {d}" for d in dif] if dif else
          ["- Mismo escenario, mismo plan, misma escala, mismo cliente de Cassandra, misma "
           "maquina. Unica diferencia declarada: CACHE_COMENTARIOS_TTL_S (0 -> 2)."])
    L += ["", "## Metricas (valores medidos, latencias en ms)", "",
          "| Metrica | Linea base | Optimizada | Variacion | Mejor si |", "|---|---:|---:|---:|---|"]
    for f in filas:
        L.append(f"| {f['metrica']} | {f['linea_base']} | {f['optimizada']} | {f['variacion']} | {f['mejor_si']} |")
    L += ["", "## Integridad", "", "| Control | Linea base | Optimizada |", "|---|---|---|"]
    for k in integ["linea_base"]:
        L.append(f"| {k} | {integ['linea_base'][k]} | {integ['optimizada'][k]} |")
    if not (b["integ"] and o["integ"]):
        L.append("\nFALTA correr validar_integridad.py en alguna de las corridas.")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        tipos = ["lectura", "escritura"]
        pcts = ["p50", "p95", "p99"]
        fig, ejes = plt.subplots(1, 2, figsize=(10, 4))
        for eje, tipo in zip(ejes, tipos):
            vb = [b["res"]["medido_por_tipo"][tipo]["latencia_cliente_ms"].get(p, 0) for p in pcts]
            vo = [o["res"]["medido_por_tipo"][tipo]["latencia_cliente_ms"].get(p, 0) for p in pcts]
            x = range(len(pcts))
            eje.bar([i - 0.2 for i in x], vb, 0.4, label="linea base", color="#8c8c8c")
            eje.bar([i + 0.2 for i in x], vo, 0.4, label="optimizada", color="#1f6f8b")
            eje.set_xticks(list(x), pcts)
            eje.set_title(f"{tipo}s (fases medidas)")
            eje.set_ylabel("latencia en el cliente (ms)")
            eje.legend()
        fig.tight_layout()
        fig.savefig(DIR_EVIDENCIA / "comparacion_latencias.png", dpi=120)

        fig, eje = plt.subplots(figsize=(10, 4))
        for d, nombre, color in ((b, "linea base", "#8c8c8c"), (o, "optimizada", "#1f6f8b")):
            xs = [int(r["segundo"]) for r in d["serie"] if r["p95_ms"]]
            ys = [float(r["p95_ms"]) for r in d["serie"] if r["p95_ms"]]
            eje.plot(xs, ys, label=nombre, color=color)
        eje.set_xlabel("segundo de la prueba")
        eje.set_ylabel("p95 por segundo (ms)")
        eje.set_title("p95 de latencia a lo largo de la prueba (incluye calentamiento)")
        eje.legend()
        fig.tight_layout()
        fig.savefig(DIR_EVIDENCIA / "comparacion_p95_en_el_tiempo.png", dpi=120)
        L += ["", "## Graficos", "", "![latencias](comparacion_latencias.png)", "",
              "![p95 en el tiempo](comparacion_p95_en_el_tiempo.png)"]
    except ImportError:
        L += ["", "*matplotlib no instalado: no se generaron graficos (las tablas son la evidencia).*"]

    (DIR_EVIDENCIA / "comparacion.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"\nGuardado en {DIR_EVIDENCIA / 'comparacion.md'}")


if __name__ == "__main__":
    main()
