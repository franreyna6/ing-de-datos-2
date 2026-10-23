#!/usr/bin/env python3
"""Capa 9 - Endpoints de la API del Hito 10: cadena cliente HTTP -> API ->
adaptador -> producto (RF15, RF18, RF19, seccion 5.5).

Para cada ruta registra metodo y path, parametros, dependencia esperada, status
HTTP, tiempo de respuesta, request ID, resultado resumido, lineas de log
asociadas e interpretacion. Cada request lleva un X-Request-ID propio, que la
API devuelve y escribe en su log: asi se relacionan respuesta y log (RNF11).

Cada caso declara de antemano la CATEGORIA esperada segun el contrato del Hito 10:
  exito | vacio_valido | recurso_inexistente | error_validacion |
  dependencia_no_disponible | timeout | error_interno | api_no_alcanzable
El resultado es OK cuando la categoria observada coincide con la esperada.

Solo se ejecutan rutas de lectura (RNF6): el POST de comentarios escribe en
Cassandra y no se usa para probar conectividad.

Uso:
  python prueba_api.py                      # contra API_BASE_URL (API ya iniciada)
  python prueba_api.py --iniciar-api        # levanta la API en 127.0.0.1:8000 y la detiene al final
"""
from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode, urlparse

import api_local
from lib_conectividad import (DIR_EVIDENCIA, FALLA, INFO, OK, Config, Resultado,
                              encabezado_corrida, guardar_resultados, http, imprimir,
                              registrar_secretos)


def casos(cfg: Config) -> list[dict]:
    eq, p, inex = cfg["PRUEBA_EQUIPO"], cfg["PRUEBA_PARTIDO"], cfg["PRUEBA_PARTIDO_INEXISTENTE"]
    pc, inst = cfg["PRUEBA_CASSANDRA_PARTIDO"], cfg["PRUEBA_CASSANDRA_INSTANTE"]
    pi, d, h = cfg["PRUEBA_INFLUX_PARTIDO"], cfg["PRUEBA_INFLUX_DESDE"], cfg["PRUEBA_INFLUX_HASTA"]
    dia = d[:11]
    return [
        dict(dep="mongodb", ruta=f"/equipos/{eq}", q={}, esperado="exito",
             nota="Equipo existente del Hito 4"),
        dict(dep="mongodb", ruta="/equipos/ZZZ", q={}, esperado="recurso_inexistente",
             nota="Codigo FIFA inexistente"),
        dict(dep="mongodb", ruta=f"/equipos/{eq}/jugadores", q={"limit": 5}, esperado="exito",
             nota="Plantel paginado"),
        dict(dep="mongodb", ruta=f"/equipos/{eq}/jugadores", q={"limit": 0},
             esperado="error_validacion", nota="limit fuera de rango: se rechaza sin consultar la base"),
        dict(dep="neo4j", ruta=f"/partidos/{p}/eventos", q={"limit": 5}, esperado="exito",
             nota="Eventos de un partido con goles"),
        dict(dep="neo4j", ruta="/partidos/F2030-006/eventos", q={"limit": 5}, esperado="vacio_valido",
             nota="Partido existente sin eventos: 200 con lista vacia"),
        dict(dep="neo4j", ruta=f"/partidos/{inex}/eventos", q={}, esperado="recurso_inexistente",
             nota="Partido inexistente"),
        dict(dep="cassandra", ruta=f"/partidos/{pc}/comentarios", q={"instante": inst, "limit": 5},
             esperado="exito", nota="Particion con comentarios de la muestra del Hito 6"),
        dict(dep="cassandra", ruta=f"/partidos/{pc}/comentarios",
             q={"instante": "2029-06-22T20:03:00Z", "limit": 5}, esperado="vacio_valido",
             nota="Ventana sin comentarios"),
        dict(dep="cassandra", ruta=f"/partidos/{pc}/comentarios", q={"instante": "no-es-fecha"},
             esperado="error_validacion", nota="Instante con formato invalido"),
        dict(dep="redis", ruta=f"/sesiones/{cfg['PRUEBA_SESION']}", q={}, esperado="exito",
             nota="Sesion vigente cargada por el Hito 7 (hash con TTL)"),
        dict(dep="redis", ruta="/sesiones/no-existe-h11", q={}, esperado="recurso_inexistente",
             nota="Sesion ausente o expirada"),
        dict(dep="influxdb", ruta=f"/partidos/{pi}/estadisticas", q={"desde": d, "hasta": h},
             esperado="exito", nota="Ventana acotada con puntos"),
        dict(dep="influxdb", ruta=f"/partidos/{pi}/estadisticas",
             q={"desde": dia + "09:00:00Z", "hasta": dia + "09:15:00Z"}, esperado="vacio_valido",
             nota="Ventana sin puntos (antes del partido)"),
        dict(dep="influxdb", ruta=f"/partidos/{pi}/estadisticas", q={"desde": h, "hasta": d},
             esperado="error_validacion", nota="desde > hasta"),
        dict(dep="iris", ruta=f"/partidos/{p}/detalle", q={}, esperado="exito",
             nota="Entidad compleja Partido del Hito 9"),
        dict(dep="iris", ruta=f"/partidos/{inex}/detalle", q={}, esperado="recurso_inexistente",
             nota="Objeto inexistente"),
    ]


_LISTAS = ("eventos", "comentarios", "puntos", "jugadores")


def categorizar(status: int | None, error: str, cuerpo: dict) -> str:
    if status is None:
        return "timeout" if error == "timeout" else "api_no_alcanzable"
    if status == 200:
        for k in _LISTAS:
            if k in cuerpo and cuerpo[k] == []:
                return "vacio_valido"
        return "exito"
    return {400: "error_validacion", 422: "error_validacion", 404: "recurso_inexistente",
            503: "dependencia_no_disponible", 504: "timeout", 500: "error_interno"}.get(
        status, f"http_{status}")


def resumir(cuerpo: dict) -> str:
    if "error" in cuerpo:
        e = cuerpo["error"]
        return f"{e.get('code')}: {e.get('message')}"
    for k in _LISTAS:
        if k in cuerpo:
            return f"{len(cuerpo[k])} {k}"
    if "dependencias" in cuerpo:
        return ", ".join(f"{d['fuente']}={'si' if d['disponible'] else 'no'}"
                         for d in cuerpo["dependencias"])
    return json.dumps(cuerpo, ensure_ascii=False)[:160]


def llamar(base: str, ruta: str, q: dict, timeout: float, rid: str):
    url = base.rstrip("/") + ruta + (("?" + urlencode(q)) if q else "")
    t0 = time.perf_counter()
    st, hdr, cuerpo, err = http("GET", url, timeout, {"X-Request-ID": rid, "Accept": "application/json"})
    ms = (time.perf_counter() - t0) * 1000
    try:
        datos = json.loads(cuerpo) if cuerpo else {}
    except ValueError:
        datos = {"crudo": cuerpo[:200].decode(errors="replace")}
    rid_resp = {k.lower(): v for k, v in hdr.items()}.get("x-request-id", "")
    return url, st, err, datos, ms, rid_resp


def ejecutar(cfg: Config, base: str, log_api: Path | None, timeout_cliente: float = 20.0,
             etiqueta: str = "") -> list[Resultado]:
    registrar_secretos(cfg.secretos())
    res: list[Resultado] = []
    prefijo = "h11" + (f"-{etiqueta}" if etiqueta else "")

    # 0) API no alcanzable: un puerto donde no hay API (distinto de dependencia caida).
    u = urlparse(base)
    falso = f"{u.scheme}://{u.hostname}:{(u.port or 80) + 99}"
    url, st, err, datos, ms, _ = llamar(falso, "/salud", {}, 3, f"{prefijo}-noapi")
    res.append(imprimir(Resultado(
        "api", "api", "GET /salud contra un puerto sin API", OK if st is None else FALLA,
        f"sin respuesta HTTP ({err}): API no alcanzable", objetivo=url,
        cliente="HTTP (urllib)", duracion_ms=ms, esperado="api_no_alcanzable",
        responde="Como se ve 'API caida' frente a 'API arriba con una dependencia caida'?",
        extra={"categoria": "api_no_alcanzable", "caso": "negativo"})))

    # 1) /salud: chequeo profundo de las seis fuentes en cada llamada.
    rid = f"{prefijo}-salud-{uuid.uuid4().hex[:4]}"
    url, st, err, datos, ms, rid_resp = llamar(base, "/salud", {}, timeout_cliente, rid)
    if st is None:
        res.append(imprimir(Resultado(
            "api", "api", "GET /salud", FALLA, f"API no alcanzable en {base} ({err}); "
            "las pruebas de rutas no se ejecutan", objetivo=url, duracion_ms=ms,
            extra={"categoria": categorizar(st, err, datos)})))
        return res
    res.append(imprimir(Resultado(
        "api", "api", "GET /salud (chequeo de las 6 fuentes)", INFO,
        f"HTTP {st} en {ms:.0f} ms | {resumir(datos)}", objetivo=url, cliente="HTTP (urllib)",
        duracion_ms=ms, responde="Que informa hoy el endpoint de salud del Hito 10?",
        no_permite="Distinguir caida, timeout, credencial o contexto: solo devuelve un booleano por "
                   "fuente y siempre HTTP 200",
        extra={"status": st, "request_id": rid_resp, "categoria": categorizar(st, err, datos),
               "dependencias": datos.get("dependencias"),
               "log": api_local.lineas_de(log_api, rid) if log_api else []})))

    # 2) Rutas principales por producto.
    for i, c in enumerate(casos(cfg), 1):
        rid = f"{prefijo}-{i:02d}-{uuid.uuid4().hex[:4]}"
        url, st, err, datos, ms, rid_resp = llamar(base, c["ruta"], c["q"], timeout_cliente, rid)
        cat = categorizar(st, err, datos)
        time.sleep(0.05)  # deja que el log de la request llegue al archivo
        log = api_local.lineas_de(log_api, rid) if log_api else []
        coincide = cat == c["esperado"]
        res.append(imprimir(Resultado(
            c["dep"], "api", f"GET {c['ruta']}" + (f"?{urlencode(c['q'])}" if c["q"] else ""),
            OK if coincide else FALLA,
            f"HTTP {st} {cat} | {resumir(datos)}" if st else f"sin respuesta ({err})",
            objetivo=url, cliente="HTTP (urllib) -> API Hito 10", duracion_ms=ms,
            esperado=c["esperado"],
            responde=c["nota"],
            no_permite="Rendimiento: una respuesta correcta no mide capacidad (Hito 12).",
            extra={"status": st, "request_id": rid_resp, "request_id_enviado": rid,
                   "categoria": cat, "parametros": c["q"], "log": log,
                   "coincide_con_contrato": coincide})))
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--iniciar-api", action="store_true",
                    help="levanta la API del Hito 10 en 127.0.0.1:8000 con esta configuracion")
    ap.add_argument("--puerto", type=int, default=8000)
    ap.add_argument("--log-api", help="archivo de log de una API ya iniciada (para correlacionar)")
    a = ap.parse_args()
    cfg = Config()
    enc = encabezado_corrida("Pruebas de la API del Hito 10", cfg)
    print(enc)
    proc, log = None, Path(a.log_api) if a.log_api else None
    base = cfg["API_BASE_URL"]
    if a.iniciar_api:
        log = DIR_EVIDENCIA / "logs" / "crudos" / "api.log"
        puerto = api_local.puerto_libre(a.puerto)
        proc = api_local.iniciar(cfg, puerto, log)
        base = f"http://127.0.0.1:{puerto}"
        print(f"# API iniciada en {base}" if proc else "# la API NO quedo lista (ver log)")
    try:
        res = ejecutar(cfg, base, log)
    finally:
        api_local.detener(proc)
    if log:
        api_local.copiar_redactado(log, DIR_EVIDENCIA / "logs" / "api_redactado.log")
    guardar_resultados("api", res, enc)


if __name__ == "__main__":
    main()
