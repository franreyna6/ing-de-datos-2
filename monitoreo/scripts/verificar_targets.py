"""Verifica que Prometheus este leyendo cada target y guarda la evidencia (RF2, RF3, 5.2).

Que hace:
  1. Espera a que Prometheus, Alertmanager y Grafana respondan.
  2. Lee /api/v1/targets: por cada target, job, componente, mecanismo, estado
     (UP/DOWN), ultimo error y duracion del ultimo scrape.
  3. Cuenta las reglas de alerta cargadas y su estado.
  4. Lista, por job, cuantas metricas expone (y los primeros nombres), para
     poder decir con evidencia que una base esta monitoreada (5.1).
  5. Ejecuta las consultas PromQL documentadas en docs/metricas_y_consultas.md
     y guarda su resultado.

Salida (sin secretos):
  evidencia/prometheus_targets.json   ultima verificacion (estructura completa)
  evidencia/prometheus_targets.md     la misma informacion en tabla
  evidencia/resultados_sin_secretos/verificacion_<fecha>.json  historial

Procedimiento para un target DOWN: ver la columna "ultimo error" y seguir
README.md, seccion "Investigar un target DOWN".

Uso:
  python scripts/verificar_targets.py            # termina con codigo 1 si hay targets DOWN
  python scripts/verificar_targets.py --esperar 60
"""
from __future__ import annotations

import argparse
import sys
import time
import urllib.parse

from lib_monitoreo import (ALERTMANAGER, DIR_EVIDENCIA, DIR_RESULTADOS, GRAFANA, PROMETHEUS,
                           ahora_utc, aviso, escribir_json, escribir_texto, esperar, http_json,
                           info, info_git, iso, paso, prom_consulta)

# Consultas PromQL documentadas (RF8). Misma lista que docs/metricas_y_consultas.md.
CONSULTAS = [
    {"id": "Q1", "nombre": "Targets UP por job", "unidad": "1 = UP, 0 = DOWN", "ventana": "instantanea",
     "expr": "up"},
    {"id": "Q2", "nombre": "Throughput de la API", "unidad": "requests/s", "ventana": "1 min",
     "expr": "sum(rate(fixture_api_requests_total[1m]))"},
    {"id": "Q3", "nombre": "Latencia p95 de la API", "unidad": "segundos", "ventana": "1 min",
     "expr": "histogram_quantile(0.95, sum by (le) (rate(fixture_api_request_duration_seconds_bucket[1m])))"},
    {"id": "Q4", "nombre": "Tasa de errores 5xx de la API", "unidad": "proporcion (0-1)", "ventana": "1 min",
     "expr": 'sum(rate(fixture_api_requests_total{estado=~"5.."}[1m])) / sum(rate(fixture_api_requests_total[1m]))'},
    {"id": "Q5", "nombre": "Latencia p95 por base", "unidad": "segundos", "ventana": "1 min",
     "expr": "histogram_quantile(0.95, sum by (le, fuente) (rate(fixture_dependencia_duration_seconds_bucket[1m])))"},
    {"id": "Q6", "nombre": "Disponibilidad por base vista por la API", "unidad": "1 = disponible", "ventana": "instantanea",
     "expr": "fixture_dependencia_disponible"},
    {"id": "Q7", "nombre": "Tasa de aciertos de la cache de comentarios", "unidad": "proporcion (0-1)", "ventana": "1 min",
     "expr": 'sum(rate(fixture_cache_comentarios_total{estado="HIT"}[1m])) / sum(rate(fixture_cache_comentarios_total{estado=~"HIT|MISS"}[1m]))'},
    {"id": "Q8", "nombre": "Memoria de Redis usada / maxima", "unidad": "proporcion (0-1)", "ventana": "instantanea",
     "expr": "redis_memory_used_bytes / redis_memory_max_bytes"},
    {"id": "Q9", "nombre": "Sondas externas que fallan", "unidad": "1 = OK, 0 = falla", "ventana": "instantanea",
     "expr": "probe_success"},
    {"id": "Q10", "nombre": "Escrituras en Cassandra por partido", "unidad": "escrituras/s", "ventana": "1 min",
     "expr": "sum by (partido) (rate(fixture_comentarios_creados_total[1m]))"},
]


def leer_targets() -> list[dict]:
    st, js = http_json("GET", f"{PROMETHEUS}/api/v1/targets?state=active", timeout=15)
    if st != 200 or not js:
        return []
    filas = []
    for t in js["data"]["activeTargets"]:
        lab = t.get("labels", {})
        filas.append({
            "job": lab.get("job", t.get("scrapePool")),
            "componente": lab.get("componente", ""),
            "mecanismo": lab.get("mecanismo", ""),
            "capa": lab.get("capa", ""),
            "hito": lab.get("hito", ""),
            "instance": lab.get("instance", ""),
            "scrape_url": t.get("scrapeUrl", ""),
            "estado": t.get("health", "unknown").upper(),
            "ultimo_error": t.get("lastError", ""),
            "duracion_ultimo_scrape_s": round(float(t.get("lastScrapeDuration", 0) or 0), 4),
            "ultimo_scrape": t.get("lastScrape", ""),
        })
    # En los jobs de sonda, "UP" solo dice que el blackbox_exporter respondio; si
    # la base acepto la conexion lo dice probe_success. Se agregan las dos cosas.
    sondas = {(r["metric"].get("job"), r["metric"].get("instance")): r["value"][1]
              for r in prom_consulta("probe_success")}
    for f in filas:
        if f["job"].startswith("sonda-"):
            v = sondas.get((f["job"], f["instance"]))
            f["sonda_ok"] = None if v is None else v == "1"
    return sorted(filas, key=lambda f: (f["capa"], f["job"], f["instance"]))


def metricas_por_job(jobs: list[str]) -> dict:
    res = {}
    for job in jobs:
        sel = urllib.parse.quote(f'{{job="{job}"}}')
        st, js = http_json("GET", f"{PROMETHEUS}/api/v1/label/__name__/values?match[]={sel}", timeout=15)
        nombres = js.get("data", []) if st == 200 and js else []
        propios = [n for n in nombres if not n.startswith(("scrape_", "up", "go_", "process_",
                                                           "promhttp_", "python_"))]
        res[job] = {"cantidad_de_metricas": len(nombres), "ejemplos": propios[:25]}
    return res


def reglas() -> dict:
    st, js = http_json("GET", f"{PROMETHEUS}/api/v1/rules?type=alert", timeout=15)
    if st != 200 or not js:
        return {}
    out = {}
    for g in js["data"]["groups"]:
        for r in g["rules"]:
            out[r["name"]] = {"grupo": g["name"], "estado": r.get("state", ""),
                              "severidad": r.get("labels", {}).get("severidad", ""),
                              "salud": r.get("health", "")}
    return out


def ejecutar_consultas() -> list[dict]:
    out = []
    for c in CONSULTAS:
        res = prom_consulta(c["expr"])
        valores = []
        for r in res[:20]:
            etiquetas = {k: v for k, v in r["metric"].items() if k in ("job", "fuente", "componente",
                                                                       "partido", "instance", "__name__")}
            valores.append({"etiquetas": etiquetas, "valor": r["value"][1]})
        out.append({**c, "resultado": valores})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--esperar", type=int, default=0,
                    help="segundos a esperar a que los targets pasen a UP antes de verificar")
    a = ap.parse_args(argv)

    paso("Verificando Prometheus, Alertmanager y Grafana")
    ok_p = esperar(f"{PROMETHEUS}/-/ready", 60, "Prometheus")
    ok_a = esperar(f"{ALERTMANAGER}/-/ready", 30, "Alertmanager")
    ok_g = esperar(f"{GRAFANA}/api/health", 60, "Grafana")
    if not ok_p:
        aviso("Sin Prometheus no hay nada que verificar. Correr scripts/iniciar_monitoreo primero.")
        return 2

    fin = time.monotonic() + a.esperar
    while True:
        targets = leer_targets()
        caidos = [t for t in targets if t["estado"] != "UP" or t.get("sonda_ok") is False]
        if not caidos or time.monotonic() >= fin:
            break
        time.sleep(5)

    momento = ahora_utc()
    jobs = sorted({t["job"] for t in targets})
    datos = {
        "fecha_utc": iso(momento),
        "git": info_git(),
        "servicios": {"prometheus_listo": ok_p, "alertmanager_listo": ok_a, "grafana_listo": ok_g},
        "resumen": {"targets": len(targets),
                    "up": sum(1 for t in targets if t["estado"] == "UP" and t.get("sonda_ok") is not False),
                    "down": sum(1 for t in targets if t["estado"] != "UP"),
                    "sondas_fallidas": sum(1 for t in targets if t.get("sonda_ok") is False)},
        "targets": targets,
        "reglas_de_alerta": reglas(),
        "metricas_por_job": metricas_por_job(jobs),
        "consultas_documentadas": ejecutar_consultas(),
    }

    r = datos["resumen"]
    paso(f"Targets: {r['up']} UP, {r['down']} DOWN, {r['sondas_fallidas']} sondas que fallan")
    for t in targets:
        marca = "UP  " if t["estado"] == "UP" else "DOWN"
        if t.get("sonda_ok") is False:
            marca = "FALLA"
        info(f"{marca} {t['job']:<13} {t['componente']:<10} {t['instance']:<40} {t['ultimo_error'][:70]}")

    escribir_json(DIR_EVIDENCIA / "prometheus_targets.json", datos)
    escribir_json(DIR_RESULTADOS / f"verificacion_{momento.strftime('%Y%m%d-%H%M%S')}.json", datos)
    escribir_texto(DIR_EVIDENCIA / "prometheus_targets.md", a_markdown(datos))
    info("Evidencia: monitoreo/evidencia/prometheus_targets.json y .md")
    return 1 if caidos else 0


def a_markdown(d: dict) -> str:
    g = d["git"]
    l = ["# Verificacion de targets de Prometheus", "",
         f"- Fecha (UTC): {d['fecha_utc']}",
         f"- Commit: `{g.get('commit_corto', '')}` (rama {g.get('rama', '')}"
         f"{', con cambios sin commitear en api/ o monitoreo/' if g.get('cambios_sin_commit_en_api_o_monitoreo') else ''})",
         f"- Generado por: `monitoreo/scripts/verificar_targets.py`",
         f"- Resultado: **{d['resumen']['up']} UP / {d['resumen']['down']} DOWN / "
         f"{d['resumen']['sondas_fallidas']} sondas que fallan** de {d['resumen']['targets']} targets", "",
         "En los jobs `sonda-*`, *Estado* es el del blackbox_exporter y *Sonda* dice si la base acepto la conexion "
         "(`probe_success`).", "",
         "## Targets", "",
         "| Job | Componente | Capa | Mecanismo | Instancia | Estado | Sonda | Ultimo scrape (s) | Ultimo error |",
         "| :-- | :-- | :-- | :-- | :-- | :-- | :-- | --: | :-- |"]
    for t in d["targets"]:
        sonda = {True: "OK", False: "FALLA", None: "-"}[t.get("sonda_ok")]
        l.append(f"| {t['job']} | {t['componente']} | {t['capa']} | {t['mecanismo']} | `{t['instance']}` | "
                 f"{t['estado']} | {sonda} | {t['duracion_ultimo_scrape_s']} | {t['ultimo_error'][:90] or '-'} |")
    l += ["", "## Metricas expuestas por job", "", "| Job | Cantidad | Ejemplos |", "| :-- | --: | :-- |"]
    for job, m in d["metricas_por_job"].items():
        l.append(f"| {job} | {m['cantidad_de_metricas']} | {', '.join(m['ejemplos'][:8]) or '-'} |")
    l += ["", "## Reglas de alerta cargadas", "", "| Alerta | Grupo | Severidad | Estado | Salud |",
          "| :-- | :-- | :-- | :-- | :-- |"]
    for n, r in d["reglas_de_alerta"].items():
        l.append(f"| {n} | {r['grupo']} | {r['severidad']} | {r['estado']} | {r['salud']} |")
    l += ["", "## Consultas PromQL documentadas (valor al momento de la verificacion)", ""]
    for c in d["consultas_documentadas"]:
        vals = "; ".join(
            f"{','.join(f'{k}={v}' for k, v in r['etiquetas'].items() if k != '__name__') or 'total'}: {float(r['valor']):.4g}"
            for r in c["resultado"][:8]) or "sin datos (sin trafico en la ventana)"
        l.append(f"- **{c['id']} {c['nombre']}** ({c['unidad']}, ventana {c['ventana']}): {vals}")
    return "\n".join(l) + "\n"


if __name__ == "__main__":
    sys.exit(main())
